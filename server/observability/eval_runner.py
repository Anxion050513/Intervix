"""Eval framework — run golden dataset through skill evaluate_answer() methods.

Reuses existing skill instances from the registry (no copy-paste of
evaluation logic). Each test case is tagged with phase="eval" in LangFuse
traces so eval runs are distinguishable from production interviews.
"""

import json
import logging
import os
import statistics
from typing import Optional

from pydantic import BaseModel

from server.ai.skills.base import SkillContext, GeneratedQuestion
from server.ai.llm import LLMFactory

logger = logging.getLogger(__name__)


# === Pydantic schemas (mirrors router.py for self-contained use) ===

class DimDiff(BaseModel):
    dimension: str
    expected: float
    actual: float
    diff: float


class EvalTestResult(BaseModel):
    test_id: str
    skill_module: str
    expected_score: float | None
    actual_score: float | None
    score_diff: float | None
    dimension_diffs: list[DimDiff]
    passed: bool


class EvalReport(BaseModel):
    total_tests: int
    passed: int
    failed: int
    avg_score_diff: float
    results: list[EvalTestResult]
    summary: str


# === Eval Runner ===

class EvalRunner:
    """Runs golden dataset test cases through skill evaluate_answer() methods."""

    SCORE_TOLERANCE = 15  # abs(actual - expected) <= 15 → passed

    def __init__(self, llm_factory: LLMFactory):
        self.llm_factory = llm_factory

    def _load_dataset(self) -> list[dict]:
        """Load the golden dataset from JSON."""
        dataset_path = os.path.join(os.path.dirname(__file__), "eval_dataset.json")
        if not os.path.exists(dataset_path):
            raise FileNotFoundError(f"Eval dataset not found: {dataset_path}")
        with open(dataset_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _get_skill(self, skill_name: str):
        """Get a skill instance from the registry, with eval-tagged llm_factory."""
        from server.ai.skills.registry import skill_registry

        # Auto-register skills if registry is empty (standalone run without server)
        if not skill_registry.get_all():
            from server.ai.skills.init_skills import register_all_skills
            register_all_skills(self.llm_factory)

        skill = skill_registry.get(skill_name)
        if skill is None:
            raise ValueError(f"Skill '{skill_name}' not found in registry")

        # Inject the eval factory (skill may have been initialized with a
        # different factory; for eval we want our own with trace tagging)
        skill.llm_factory = self.llm_factory
        return skill

    def _build_context(self, case: dict) -> SkillContext:
        """Build a SkillContext from test case context."""
        ctx_data = case.get("context", {})
        return SkillContext(
            tech_stack=ctx_data.get("tech_stack", []),
            years_experience=ctx_data.get("years_experience"),
            difficulty=ctx_data.get("difficulty", "medium"),
            session_id=f"eval:{case['test_id']}",
        )

    def _build_question(self, case: dict) -> GeneratedQuestion:
        """Build a GeneratedQuestion from test case data."""
        return GeneratedQuestion(
            text=case["question_text"],
            question_type=case.get("question_type", case["skill_module"]),
            reference_answer=case.get("reference_answer"),
        )

    def _compare(
        self, case: dict, actual: dict
    ) -> EvalTestResult:
        """Compare expected vs actual evaluation results."""
        expected_score = case.get("expected_score")
        actual_score = actual.get("score")

        # Score diff (None if warmup which has no score)
        score_diff = None
        if expected_score is not None and actual_score is not None:
            score_diff = abs(actual_score - expected_score)

        # Dimension-level diffs
        dim_diffs = []
        expected_dims = case.get("expected_dimensions", {})
        actual_dims = actual.get("score_breakdown", {})
        for dim_name, exp_val in expected_dims.items():
            act_val = actual_dims.get(dim_name, 0)
            dim_diffs.append(DimDiff(
                dimension=dim_name,
                expected=exp_val,
                actual=act_val,
                diff=abs(act_val - exp_val),
            ))

        # Pass/fail: for warmup (no score), check dimension diffs average
        if expected_score is not None and score_diff is not None:
            passed = score_diff <= self.SCORE_TOLERANCE
        elif dim_diffs:
            avg_dim_diff = sum(d.diff for d in dim_diffs) / len(dim_diffs)
            passed = avg_dim_diff <= self.SCORE_TOLERANCE
        else:
            passed = True  # nothing to compare

        return EvalTestResult(
            test_id=case["test_id"],
            skill_module=case["skill_module"],
            expected_score=expected_score,
            actual_score=actual_score,
            score_diff=score_diff,
            dimension_diffs=dim_diffs,
            passed=passed,
        )

    async def run_eval(self) -> EvalReport:
        """Load dataset, run each test case, and return a comparison report.

        Each call is traced with phase="eval" in LangFuse (when enabled).
        """
        dataset = self._load_dataset()
        results: list[EvalTestResult] = []

        for case in dataset:
            # Set eval trace context
            try:
                from server.observability.callbacks import TraceContext
                TraceContext.set(
                    session_id=f"eval:{case['test_id']}",
                    skill_module=case["skill_module"],
                    phase="eval",
                    question_id=case["test_id"],
                )
            except Exception:
                pass

            try:
                skill = self._get_skill(case["skill_module"])
                ctx = self._build_context(case)
                question = self._build_question(case)

                logger.info(
                    "Eval running: %s (%s)", case["test_id"], case["skill_module"]
                )

                actual = await skill.evaluate_answer(
                    question, case["user_answer"], ctx
                )

                result = self._compare(case, actual)
                results.append(result)

                logger.info(
                    "Eval result: %s — expected=%s actual=%s passed=%s",
                    case["test_id"],
                    case.get("expected_score"),
                    actual.get("score"),
                    result.passed,
                )

            except Exception as e:
                logger.error(
                    "Eval failed for %s: %s", case["test_id"], e, exc_info=True
                )
                results.append(EvalTestResult(
                    test_id=case["test_id"],
                    skill_module=case["skill_module"],
                    expected_score=case.get("expected_score"),
                    actual_score=None,
                    score_diff=None,
                    dimension_diffs=[],
                    passed=False,
                ))
            finally:
                try:
                    TraceContext.clear()
                except Exception:
                    pass

        # Build report
        passed_count = sum(1 for r in results if r.passed)
        failed_count = len(results) - passed_count
        score_diffs = [r.score_diff for r in results if r.score_diff is not None]
        avg_diff = statistics.mean(score_diffs) if score_diffs else 0.0

        if passed_count == len(results):
            summary = f"All {len(results)} tests passed! Average score diff: {avg_diff:.1f}"
        elif passed_count == 0:
            summary = f"All {len(results)} tests FAILED. Average score diff: {avg_diff:.1f} — prompts may need revision."
        else:
            summary = (
                f"{passed_count}/{len(results)} tests passed, "
                f"{failed_count} failed. Average score diff: {avg_diff:.1f}"
            )

        return EvalReport(
            total_tests=len(results),
            passed=passed_count,
            failed=failed_count,
            avg_score_diff=round(avg_diff, 2),
            results=results,
            summary=summary,
        )
