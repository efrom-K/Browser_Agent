from agent.core.context import trim_history


def _observation(tool_use_id: str, action_text: str) -> dict:
    return {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": [
                    {"type": "text", "text": action_text},
                    {"type": "text", "text": "Page: 'Example' (https://example.com)\n..."},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "xx"}},
                ],
            }
        ],
    }


def _assistant(text: str) -> dict:
    return {"role": "assistant", "content": [{"type": "text", "text": text}]}


def _initial_observation() -> dict:
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": "Task: do something\n\nPage: ..."},
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "xx"}},
        ],
    }


def test_no_trimming_when_within_limit():
    messages = [
        _initial_observation(),
        _assistant("clicking"),
        _observation("t1", "Clicked element 0"),
    ]

    result = trim_history(messages, keep_last=3)

    assert result == messages


def test_older_observations_are_trimmed():
    messages = [
        _initial_observation(),
        _assistant("a1"),
        _observation("t1", "Clicked element 0"),
        _assistant("a2"),
        _observation("t2", "Clicked element 1"),
        _assistant("a3"),
        _observation("t3", "Clicked element 2"),
    ]

    result = trim_history(messages, keep_last=1)

    # First observation and assistant messages are untouched.
    assert result[0] == messages[0]
    assert result[1] == messages[1]
    assert result[3] == messages[3]
    assert result[5] == messages[5]

    # Older observations (t1, t2) lost their page description/screenshot...
    for i in (2, 4):
        content = result[i]["content"][0]["content"]
        assert len(content) == 2
        assert content[0] == messages[i]["content"][0]["content"][0]
        assert content[1] == {"type": "text", "text": "[older page observation omitted to save context]"}

    # ...but the most recent observation (t3) is untouched.
    assert result[6] == messages[6]


def test_keep_last_zero_trims_everything_but_the_first_observation():
    messages = [
        _initial_observation(),
        _assistant("a1"),
        _observation("t1", "Clicked element 0"),
    ]

    result = trim_history(messages, keep_last=0)

    assert result[0] == messages[0]
    assert len(result[2]["content"][0]["content"]) == 2


def test_ask_user_replies_are_not_treated_as_observations():
    messages = [
        _initial_observation(),
        _assistant("a1"),
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": [{"type": "text", "text": "playwright"}]}
            ],
        },
        _assistant("a2"),
        _observation("t2", "Clicked element 1"),
    ]

    result = trim_history(messages, keep_last=0)

    # The ask_user reply (single-block tool_result) is left alone.
    assert result[2] == messages[2]
