"""Live-only local LLM check. Requires Ollama and the selected model already installed."""
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.agent import DataAgent
from app.llm import OllamaPlanner, AgentUnavailable, AgentPolicyError
from app.pipeline import synthetic


def main():
    history = synthetic()
    students = synthetic(seed=43).iloc[:5].drop(columns='deserto').copy()
    students['periodo'] = 20242
    with tempfile.TemporaryDirectory() as root:
        planner = OllamaPlanner()
        agent = DataAgent(root, planner=planner)
        _, probabilities, metrics, _ = agent.run(history, students)
        assert len(probabilities) == 5 and all(0 <= p <= 1 for p in probabilities)
        assert metrics['train_rows'] == 400 and metrics['test_rows'] == 200
        assert agent.decisions[-1]['action'] == 'finish'
        assert len(agent.decisions) <= 10 and len(agent.harness.trace) <= 10
        print(json.dumps({'status': 'passed', 'provider': 'ollama_local', 'model': planner.model,
                          'mode': 'llm', 'decisions': agent.decisions, 'data_kind': 'synthetic'}))


if __name__=='__main__':
    try:
        main()
    except (AgentUnavailable, AgentPolicyError) as exc:
        print('LLM live check not passed:', str(exc), file=sys.stderr)
        raise SystemExit(2)
