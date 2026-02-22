from novaadapt_shared.model_router import ModelEndpoint, ModelRouter


def _transport_factory(outputs):
    def transport(endpoint, _messages, _temperature, _max_tokens, _timeout):
        return outputs[endpoint.name]

    return transport


def test_single_strategy_uses_default_model():
    endpoints = [
        ModelEndpoint(name="a", model="alpha", base_url="http://localhost:1"),
        ModelEndpoint(name="b", model="beta", base_url="http://localhost:2"),
    ]
    router = ModelRouter(
        endpoints=endpoints,
        default_model="a",
        transport=_transport_factory({"a": "ok", "b": "no"}),
    )

    result = router.chat(messages=[{"role": "user", "content": "hello"}])
    assert result.model_name == "a"
    assert result.content == "ok"


def test_vote_strategy_returns_majority_content():
    endpoints = [
        ModelEndpoint(name="a", model="alpha", base_url="http://localhost:1"),
        ModelEndpoint(name="b", model="beta", base_url="http://localhost:2"),
        ModelEndpoint(name="c", model="gamma", base_url="http://localhost:3"),
    ]
    router = ModelRouter(
        endpoints=endpoints,
        default_model="a",
        transport=_transport_factory(
            {
                "a": '{"actions": [{"type": "click", "target": "OK"}]}',
                "b": '{"actions": [{"type": "click", "target": "OK"}]}',
                "c": '{"actions": [{"type": "type", "target": "Search", "value": "query"}]}',
            }
        ),
    )

    result = router.chat(
        messages=[{"role": "user", "content": "do task"}],
        strategy="vote",
        candidate_models=["a", "b", "c"],
    )

    assert result.strategy == "vote"
    assert "click" in result.content
    assert len(result.votes) == 3
