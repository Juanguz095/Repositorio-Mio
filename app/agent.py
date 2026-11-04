"""Bounded orchestration with deterministic and local-LLM planners."""
from app.pipeline import Harness
from app.llm import AgentPolicyError


class DataAgent:
    role = 'Preparar datos académicos y estimar riesgo; nunca aprobar ni publicar casos'

    def __init__(self, root, max_steps=10, planner=None):
        self.harness = Harness(root, max_steps=max_steps)
        self.planner = planner
        self.decisions = []

    @property
    def metadata(self):
        return {'mode': 'llm' if self.planner else 'rules',
                'model': getattr(self.planner, 'model', None), 'decisions': self.decisions}

    def run(self, history=None, students=None, history_path=None, students_path=None):
        h = self.harness
        if history_path is not None:
            history = h.call('read_excel', path=history_path)
            students = h.call('read_excel', path=students_path)
        if self.planner is None:
            history, history_quality = h.call('clean', df=history)
            students, student_quality = h.call('clean', df=students)
            self._temporal(history, students)
            model, metrics = h.call('train', df=history)
            probabilities = h.call('predict', model=model, df=students)
            return students, probabilities, metrics, {'history': history_quality, 'students': student_quality}

        # The LLM selects among currently valid tools. It receives neither rows,
        # filenames, SQL, reviewer credentials nor a way to supply tool arguments.
        cleaned = {}
        model = None
        probabilities = None
        metrics = None
        for turn in range(h.max_steps):
            allowed = [f'clean_{name}' for name in ('history', 'students') if name not in cleaned]
            if not allowed:
                allowed = ['train'] if model is None else ['predict'] if probabilities is None else ['finish']
            action = self.planner.choose(allowed, {'history_rows': len(history), 'student_rows': len(students),
                'completed': list(cleaned), 'trained': model is not None, 'predicted': probabilities is not None})
            if action not in allowed:
                raise AgentPolicyError('Acción fuera del estado permitido')
            self.decisions.append({'turn': turn+1, 'action': action})
            if action.startswith('clean_'):
                name = action.removeprefix('clean_')
                cleaned[name] = h.call('clean', df=history if name == 'history' else students)
            elif action == 'train':
                self._temporal(cleaned['history'][0], cleaned['students'][0])
                model, metrics = h.call('train', df=cleaned['history'][0])
            elif action == 'predict':
                probabilities = h.call('predict', model=model, df=cleaned['students'][0])
            else:
                return cleaned['students'][0], probabilities, metrics, {
                    name: value[1] for name, value in cleaned.items()}
        raise AgentPolicyError('Presupuesto de decisiones del LLM agotado')

    @staticmethod
    def _temporal(history, students):
        if students.periodo.min() <= history.periodo.max():
            raise ValueError('Los alumnos a evaluar deben ser posteriores al histórico')
