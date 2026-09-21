from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WorkflowStep:
    step_id: str
    operation: str
    parameters: dict[str, Any]
    preconditions: tuple[str, ...]
    postconditions: tuple[str, ...]
    timeout_seconds: int | None


@dataclass(frozen=True)
class SecurityWorkflow:
    workflow_id: str
    action: str
    target_nf: str
    target: dict[str, str]
    preconditions: tuple[str, ...]
    rollback_action: str
    timeout_seconds: int | None
    evidence: dict[str, Any]
    steps: tuple[WorkflowStep, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "action": self.action,
            "target_nf": self.target_nf,
            "target": self.target,
            "preconditions": list(self.preconditions),
            "rollback_action": self.rollback_action,
            "timeout_seconds": self.timeout_seconds,
            "evidence": self.evidence,
            "steps": [
                {
                    "step_id": step.step_id,
                    "operation": step.operation,
                    "parameters": step.parameters,
                    "preconditions": list(step.preconditions),
                    "postconditions": list(step.postconditions),
                    "timeout_seconds": step.timeout_seconds,
                }
                for step in self.steps
            ],
        }


class SecIRCompiler:
    """Compile approved decisions into typed, rollback-aware workflows.

    This compiler creates a plan only. Adapter execution remains a separate
    authenticated step.
    """

    ACTIONS = {
        "rate_limit": {
            "operation": "apply_tc_rate_limit",
            "rollback": "restore_fq_codel",
            "postcondition": "qdisc_is_tbf",
            "rollback_postcondition": "qdisc_is_fq_codel",
        },
        "alert_operator": {
            "operation": "create_operator_alert",
            "rollback": "none",
            "postcondition": "audit_record_written",
            "rollback_postcondition": "none",
        },
        "isolate_test_ue": {
            "operation": "isolate_test_ue",
            "rollback": "restore_test_ue_policy",
            "postcondition": "test_ue_isolated",
            "rollback_postcondition": "test_ue_policy_restored",
        },
        "change_test_policy": {
            "operation": "change_test_policy",
            "rollback": "restore_test_policy",
            "postcondition": "policy_change_audited",
            "rollback_postcondition": "test_policy_restored",
        },
    }

    def validate_evidence(self, evidence: dict[str, Any]) -> None:
        if not evidence:
            raise ValueError("workflow requires evidence references")
        if evidence.get("autonomous_response_eligible") is False:
            raise ValueError("evidence is not eligible for autonomous response")

    def validate(self, workflow: SecurityWorkflow) -> None:
        if not workflow.steps:
            raise ValueError("workflow must contain at least one step")
        if not workflow.rollback_action:
            raise ValueError("workflow must declare rollback")
        if not workflow.evidence:
            raise ValueError("workflow must retain evidence references")

    def execute(self, workflow: SecurityWorkflow, executor: Any) -> dict[str, Any]:
        """Execute through an already-authorized adapter and return audit state."""
        self.validate(workflow)
        result = executor.execute(
            type(
                "CompiledDecision",
                (),
                {
                    "allowed": True,
                    "decision_id": workflow.workflow_id,
                    "target_nf": workflow.target_nf,
                    "target": workflow.target,
                    "action": workflow.action,
                    "duration": workflow.timeout_seconds,
                    "reason": workflow.evidence.get("reason", "compiled_workflow"),
                    "confidence": workflow.evidence.get("confidence", 1.0),
                },
            )()
        )
        return {"workflow_id": workflow.workflow_id, "status": "executed", "adapter_result": result}

    def compile(self, decision: Any, *, evidence: dict[str, Any] | None = None) -> SecurityWorkflow:
        if not decision.allowed:
            raise ValueError("rejected decisions cannot become workflows")
        action_spec = self.ACTIONS.get(decision.action)
        if action_spec is None:
            raise ValueError(f"no SecIR workflow template for action: {decision.action}")
        evidence = evidence or {}
        self.validate_evidence(evidence)
        preconditions = (
            "policy_allowed",
            "target_allow_listed",
            "confidence_threshold_met",
            "rollback_available",
        )
        step = WorkflowStep(
            step_id="enforce",
            operation=action_spec["operation"],
            parameters={"target_nf": decision.target_nf, **decision.target},
            preconditions=preconditions,
            postconditions=(action_spec["postcondition"],),
            timeout_seconds=decision.duration,
        )
        return SecurityWorkflow(
            workflow_id=decision.decision_id,
            action=decision.action,
            target_nf=decision.target_nf,
            target=decision.target,
            preconditions=preconditions,
            rollback_action=action_spec["rollback"],
            timeout_seconds=decision.duration,
            evidence=evidence,
            steps=(step,),
        )