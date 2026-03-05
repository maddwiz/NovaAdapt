import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
import json

from novaadapt_shared.model_router import ModelEndpoint, ModelRouter


def _transport_factory(outputs):
    def transport(endpoint, _messages, _temperature, _max_tokens, _timeout):
        return outputs[endpoint.name]

    return transport


class ModelRouterTests(unittest.TestCase):
    def test_single_strategy_uses_default_model(self):
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
        self.assertEqual(result.model_name, "a")
        self.assertEqual(result.content, "ok")

    def test_vote_strategy_returns_majority_content(self):
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

        self.assertEqual(result.strategy, "vote")
        self.assertIn("click", result.content)
        self.assertEqual(len(result.votes), 3)

    def test_single_strategy_fallback_on_primary_failure(self):
        endpoints = [
            ModelEndpoint(name="primary", model="alpha", base_url="http://localhost:1"),
            ModelEndpoint(name="backup", model="beta", base_url="http://localhost:2"),
        ]

        def transport(endpoint, _messages, _temperature, _max_tokens, _timeout):
            if endpoint.name == "primary":
                raise RuntimeError("primary unavailable")
            return "backup ok"

        router = ModelRouter(endpoints=endpoints, default_model="primary", transport=transport)
        result = router.chat(messages=[{"role": "user", "content": "hello"}], fallback_models=["backup"])

        self.assertEqual(result.model_name, "backup")
        self.assertEqual(result.content, "backup ok")
        self.assertIn("primary", result.errors)

    def test_vote_strategy_continues_when_one_candidate_fails(self):
        endpoints = [
            ModelEndpoint(name="a", model="alpha", base_url="http://localhost:1"),
            ModelEndpoint(name="b", model="beta", base_url="http://localhost:2"),
            ModelEndpoint(name="c", model="gamma", base_url="http://localhost:3"),
        ]

        def transport(endpoint, _messages, _temperature, _max_tokens, _timeout):
            if endpoint.name == "c":
                raise RuntimeError("timeout")
            return "same-response"

        router = ModelRouter(endpoints=endpoints, default_model="a", transport=transport)
        result = router.chat(
            messages=[{"role": "user", "content": "do task"}],
            strategy="vote",
            candidate_models=["a", "b", "c"],
        )
        self.assertIn(result.model_name, {"a", "b"})
        self.assertEqual(len(result.votes), 2)
        self.assertIn("c", result.errors)

    def test_vote_strategy_uses_default_candidates_and_stable_winner(self):
        endpoints = [
            ModelEndpoint(name="a", model="alpha", base_url="http://localhost:1"),
            ModelEndpoint(name="b", model="beta", base_url="http://localhost:2"),
            ModelEndpoint(name="c", model="gamma", base_url="http://localhost:3"),
            ModelEndpoint(name="d", model="delta", base_url="http://localhost:4"),
        ]
        router = ModelRouter(
            endpoints=endpoints,
            default_model="b",
            default_vote_candidates=3,
            transport=_transport_factory(
                {
                    "a": '{"actions":[{"target":"OK","type":"click"}]}',
                    "b": '{"actions":[{"type":"click","target":"OK"}]}',
                    "c": '{"actions":[{"type":"type","target":"Search","value":"x"}]}',
                }
            ),
        )

        result = router.chat(messages=[{"role": "user", "content": "do task"}], strategy="vote")
        self.assertEqual(result.attempted_models, ["b", "a", "c"])
        self.assertEqual(set(result.votes.keys()), {"a", "b", "c"})
        self.assertEqual(result.model_name, "b")
        self.assertEqual(result.vote_summary["winner_votes"], 2)
        self.assertEqual(result.vote_summary["total_votes"], 3)

    def test_vote_strategy_quorum_is_enforced(self):
        endpoints = [
            ModelEndpoint(name="a", model="alpha", base_url="http://localhost:1"),
            ModelEndpoint(name="b", model="beta", base_url="http://localhost:2"),
            ModelEndpoint(name="c", model="gamma", base_url="http://localhost:3"),
        ]
        router = ModelRouter(
            endpoints=endpoints,
            default_model="a",
            min_vote_agreement=3,
            transport=_transport_factory({"a": "same", "b": "same", "c": "different"}),
        )

        with self.assertRaisesRegex(RuntimeError, "Vote quorum not met"):
            router.chat(
                messages=[{"role": "user", "content": "do task"}],
                strategy="vote",
                candidate_models=["a", "b", "c"],
            )

    def test_decompose_strategy_executes_subtasks_and_synthesizes(self):
        endpoints = [
            ModelEndpoint(name="planner", model="alpha", base_url="http://localhost:1"),
            ModelEndpoint(name="worker", model="beta", base_url="http://localhost:2"),
        ]

        def transport(_endpoint, messages, _temperature, _max_tokens, _timeout):
            system = str(messages[0].get("content", "")) if messages else ""
            user = str(messages[-1].get("content", "")) if messages else ""
            if "Build a concise JSON plan for decomposed execution." in system:
                return json.dumps(
                    {
                        "subtasks": [
                            {"id": "s1", "objective": "Gather price points", "model": "worker"},
                            {"id": "s2", "objective": "Draft buyer message", "model": "planner"},
                        ]
                    }
                )
            if "You are solving one subtask in a decomposed workflow." in system:
                if "Gather price points" in user:
                    return "Price points: route A is cheaper."
                if "Draft buyer message" in user:
                    return "Buyer message draft: Let's proceed with route A."
                return "Subtask complete."
            if "Synthesize final answer from subtask outputs." in system:
                return "Final plan: use route A and send the buyer message."
            return "Fallback single response."

        router = ModelRouter(endpoints=endpoints, default_model="planner", transport=transport)
        result = router.chat(
            messages=[{"role": "user", "content": "Plan trade route and buyer message"}],
            strategy="decompose",
            candidate_models=["planner", "worker"],
        )

        self.assertEqual(result.strategy, "decompose")
        self.assertEqual(result.model_name, "planner")
        self.assertIn("Final plan", result.content)
        self.assertEqual(result.vote_summary["subtasks_total"], 2)
        self.assertEqual(result.vote_summary["subtasks_succeeded"], 2)
        self.assertEqual(result.vote_summary["subtasks_failed"], 0)
        self.assertEqual(set(result.votes.keys()), {"s1", "s2"})
        self.assertIn("worker", result.attempted_models)
        self.assertIn("planner", result.attempted_models)

    def test_decompose_strategy_falls_back_when_planner_plan_invalid(self):
        endpoints = [ModelEndpoint(name="planner", model="alpha", base_url="http://localhost:1")]

        def transport(_endpoint, messages, _temperature, _max_tokens, _timeout):
            system = str(messages[0].get("content", "")) if messages else ""
            if "Build a concise JSON plan for decomposed execution." in system:
                return "not-json"
            return "Fallback single response."

        router = ModelRouter(endpoints=endpoints, default_model="planner", transport=transport)
        result = router.chat(
            messages=[{"role": "user", "content": "Plan a route"}],
            strategy="decompose",
        )

        self.assertEqual(result.strategy, "decompose")
        self.assertEqual(result.content, "Fallback single response.")
        self.assertEqual(result.vote_summary["fallback"], "single")
        self.assertEqual(result.vote_summary["reason"], "invalid_plan")
        self.assertIn("decompose.planner", result.errors)
        self.assertEqual(result.errors["decompose.planner"], "planner returned no usable subtasks")

    def test_decompose_strategy_does_not_invoke_single_fallback_on_success(self):
        endpoints = [ModelEndpoint(name="planner", model="alpha", base_url="http://localhost:1")]
        fallback_probe = {"calls": 0}

        def transport(_endpoint, messages, _temperature, _max_tokens, _timeout):
            if messages == [{"role": "user", "content": "Plan route"}]:
                fallback_probe["calls"] += 1
                return "Fallback single response."
            system = str(messages[0].get("content", "")) if messages else ""
            if "Build a concise JSON plan for decomposed execution." in system:
                return json.dumps({"subtasks": [{"id": "s1", "objective": "Choose the best route"}]})
            if "You are solving one subtask in a decomposed workflow." in system:
                return "Best route is corridor 7."
            if "Synthesize final answer from subtask outputs." in system:
                return "Use corridor 7."
            return "Unexpected"

        router = ModelRouter(endpoints=endpoints, default_model="planner", transport=transport)
        result = router.chat(messages=[{"role": "user", "content": "Plan route"}], strategy="decompose")

        self.assertEqual(result.content, "Use corridor 7.")
        self.assertEqual(fallback_probe["calls"], 0)

    def test_from_config_file_loads_vote_routing_settings(self):
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "models.json"
            config_path.write_text(
                json.dumps(
                    {
                        "default_model": "local",
                        "routing": {
                            "temperature": 0.1,
                            "max_tokens": 500,
                            "timeout_seconds": 20,
                            "default_vote_candidates": 2,
                            "min_vote_agreement": 2,
                            "decompose_max_subtasks": 6,
                        },
                        "models": [
                            {
                                "name": "local",
                                "model": "qwen",
                                "base_url": "http://localhost:11434/v1",
                            },
                            {
                                "name": "backup",
                                "model": "llama",
                                "base_url": "http://localhost:8000/v1",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            router = ModelRouter.from_config_file(config_path)
            self.assertEqual(router.default_vote_candidates, 2)
            self.assertEqual(router.min_vote_agreement, 2)
            self.assertEqual(router.decompose_max_subtasks, 6)


if __name__ == "__main__":
    unittest.main()
