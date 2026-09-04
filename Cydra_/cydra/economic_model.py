"""Bounded economic reasoning state for authorized security investigations.

Economic modeling is simulation state, not execution evidence. It lets CYDRA
reason about balances, liabilities, prices, incentives, capital requirements,
fees, slippage, and multi-step value transitions without pretending that a
simulated profitable path was externally executed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from typing import Mapping


class EconomicModelError(ValueError):
    """Raised when an economic model violates its deterministic bounds."""


def _finite(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise EconomicModelError(f"{name} must be finite")
    return value


@dataclass(frozen=True)
class EconomicState:
    """A canonical simulated economic state; never external evidence."""

    state_id: str
    balances: Mapping[str, float] = field(default_factory=dict)
    liabilities: Mapping[str, float] = field(default_factory=dict)
    prices: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.state_id.strip():
            raise EconomicModelError("state_id must not be empty")
        for group_name, group in (("balances", self.balances), ("liabilities", self.liabilities), ("prices", self.prices)):
            for key, value in group.items():
                if not str(key).strip():
                    raise EconomicModelError(f"{group_name} contains an empty key")
                _finite(float(value), f"{group_name}[{key}]")

    def fingerprint(self) -> str:
        payload = {
            "state_id": self.state_id,
            "balances": {str(k): float(v) for k, v in sorted(self.balances.items())},
            "liabilities": {str(k): float(v) for k, v in sorted(self.liabilities.items())},
            "prices": {str(k): float(v) for k, v in sorted(self.prices.items())},
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class EconomicTransition:
    """A deterministic simulated value transition between two states."""

    transition_id: str
    from_state: str
    to_state: str
    actor: str
    value_delta: float = 0.0
    fee: float = 0.0
    slippage: float = 0.0
    rationale: str = ""

    def __post_init__(self) -> None:
        for name in ("transition_id", "from_state", "to_state", "actor"):
            if not getattr(self, name).strip():
                raise EconomicModelError(f"{name} must not be empty")
        for name in ("value_delta", "fee", "slippage"):
            _finite(getattr(self, name), name)
        if self.fee < 0 or self.slippage < 0:
            raise EconomicModelError("fee and slippage must be non-negative")

    @property
    def net_value_delta(self) -> float:
        return self.value_delta - self.fee - self.slippage


@dataclass(frozen=True)
class EconomicScenario:
    """A bounded simulated path. It is never promoted to execution evidence."""

    scenario_id: str
    state_ids: tuple[str, ...]
    transition_ids: tuple[str, ...]
    attacker_capital: float = 0.0

    def __post_init__(self) -> None:
        if not self.scenario_id.strip():
            raise EconomicModelError("scenario_id must not be empty")
        if self.attacker_capital < 0 or not math.isfinite(self.attacker_capital):
            raise EconomicModelError("attacker_capital must be finite and non-negative")
        if not self.state_ids:
            raise EconomicModelError("scenario must contain at least one state")
        if len(self.transition_ids) + 1 != len(self.state_ids):
            raise EconomicModelError("scenario state/transition lengths are inconsistent")

    @property
    def simulated(self) -> bool:
        return True


@dataclass(frozen=True)
class EconomicAssessment:
    """A bounded decision signal derived from one canonical simulated scenario."""

    scenario_id: str
    net_value_delta: float
    attacker_capital: float
    capital_efficiency: float
    profitable: bool
    simulated_only: bool = True

    def __post_init__(self) -> None:
        if not self.scenario_id.strip():
            raise EconomicModelError("scenario_id must not be empty")
        _finite(self.net_value_delta, "net_value_delta")
        _finite(self.attacker_capital, "attacker_capital")
        _finite(self.capital_efficiency, "capital_efficiency")
        if self.attacker_capital < 0:
            raise EconomicModelError("attacker_capital must be non-negative")
        if not self.simulated_only:
            raise EconomicModelError("economic assessment must remain simulation-only")


@dataclass
class EconomicModel:
    """Finite economic state graph with explicit scenario and resource bounds."""

    max_states: int = 64
    max_transitions: int = 128
    max_scenario_depth: int = 8
    max_scenarios: int = 32
    max_attacker_capital: float = 1_000_000.0
    max_economic_budget: float = 1_000.0
    economic_budget_used: float = 0.0
    states: dict[str, EconomicState] = field(default_factory=dict)
    transitions: dict[str, EconomicTransition] = field(default_factory=dict)
    scenarios: dict[str, EconomicScenario] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("max_states", "max_transitions", "max_scenario_depth", "max_scenarios"):
            if getattr(self, name) < 1:
                raise EconomicModelError(f"{name} must be positive")
        if self.max_attacker_capital < 0 or not math.isfinite(self.max_attacker_capital):
            raise EconomicModelError("max_attacker_capital must be finite and non-negative")
        if self.max_economic_budget < 0 or not math.isfinite(self.max_economic_budget):
            raise EconomicModelError("max_economic_budget must be finite and non-negative")
        if self.economic_budget_used < 0 or not math.isfinite(self.economic_budget_used):
            raise EconomicModelError("economic_budget_used must be finite and non-negative")
        if self.economic_budget_used > self.max_economic_budget:
            raise EconomicModelError("economic budget already exceeds its authority")

    @property
    def remaining_economic_budget(self) -> float:
        return max(0.0, self.max_economic_budget - self.economic_budget_used)

    def consume_economic_budget(self, amount: float) -> None:
        """Spend simulation budget only; this never authorizes external execution."""
        amount = _finite(amount, "economic budget amount")
        if amount < 0:
            raise EconomicModelError("economic budget amount must be non-negative")
        if self.economic_budget_used + amount > self.max_economic_budget:
            raise EconomicModelError("economic simulation budget exhausted")
        self.economic_budget_used += amount

    def add_state(self, state: EconomicState) -> None:
        existing = self.states.get(state.state_id)
        if existing is not None:
            if existing.fingerprint() != state.fingerprint():
                raise EconomicModelError("economic state identity collision")
            return
        if len(self.states) >= self.max_states:
            raise EconomicModelError("economic state budget exhausted")
        self.states[state.state_id] = state

    def add_transition(self, transition: EconomicTransition) -> None:
        if transition.from_state not in self.states or transition.to_state not in self.states:
            raise EconomicModelError("economic transition references unknown state")
        existing = self.transitions.get(transition.transition_id)
        if existing is not None:
            if existing != transition:
                raise EconomicModelError("economic transition identity collision")
            return
        if len(self.transitions) >= self.max_transitions:
            raise EconomicModelError("economic transition budget exhausted")
        self.transitions[transition.transition_id] = transition

    def build_scenario(
        self,
        *,
        scenario_id: str,
        start_state: str,
        transition_ids: tuple[str, ...],
        attacker_capital: float,
        budget_cost: float = 1.0,
    ) -> EconomicScenario:
        if not scenario_id.strip():
            raise EconomicModelError("scenario_id must not be empty")
        if len(transition_ids) > self.max_scenario_depth:
            raise EconomicModelError("economic scenario depth limit reached")
        if attacker_capital < 0 or not math.isfinite(attacker_capital):
            raise EconomicModelError("attacker capital must be finite and non-negative")
        if attacker_capital > self.max_attacker_capital:
            raise EconomicModelError("attacker capital exceeds economic authority")
        if start_state not in self.states:
            raise EconomicModelError("scenario start state is unknown")
        existing = self.scenarios.get(scenario_id)
        if existing is not None:
            candidate = EconomicScenario(scenario_id, existing.state_ids, existing.transition_ids, attacker_capital)
            if candidate != existing:
                raise EconomicModelError("economic scenario identity collision")
            return existing
        self.consume_economic_budget(budget_cost)
        if len(self.scenarios) >= self.max_scenarios:
            # Refund the simulation budget because no scenario was committed.
            self.economic_budget_used -= float(budget_cost)
            raise EconomicModelError("economic scenario budget exhausted")
        current = start_state
        state_ids = [current]
        seen_transitions: set[str] = set()
        for transition_id in transition_ids:
            if transition_id in seen_transitions:
                self.economic_budget_used -= float(budget_cost)
                raise EconomicModelError("economic scenario repeats a transition identity")
            seen_transitions.add(transition_id)
            transition = self.transitions.get(transition_id)
            if transition is None or transition.from_state != current:
                self.economic_budget_used -= float(budget_cost)
                raise EconomicModelError("economic scenario transition chain is invalid")
            current = transition.to_state
            state_ids.append(current)
        scenario = EconomicScenario(scenario_id, tuple(state_ids), transition_ids, float(attacker_capital))
        self.scenarios[scenario_id] = scenario
        return scenario

    def scenario_net_value_delta(self, scenario: EconomicScenario) -> float:
        canonical = self.scenarios.get(scenario.scenario_id)
        if canonical != scenario:
            raise EconomicModelError("scenario is not the canonical modeled scenario")
        total = 0.0
        for transition_id in scenario.transition_ids:
            transition = self.transitions.get(transition_id)
            if transition is None:
                raise EconomicModelError("scenario contains unknown transition")
            total += transition.net_value_delta
        return _finite(total, "scenario net value delta")

    def assess_scenario(self, scenario: EconomicScenario) -> EconomicAssessment:
        """Return a simulation-only economic signal for bounded planning."""
        net = self.scenario_net_value_delta(scenario)
        efficiency = 0.0 if scenario.attacker_capital == 0 else net / scenario.attacker_capital
        return EconomicAssessment(
            scenario_id=scenario.scenario_id,
            net_value_delta=net,
            attacker_capital=scenario.attacker_capital,
            capital_efficiency=_finite(efficiency, "capital efficiency"),
            profitable=net > 0,
        )

    def is_simulated_only(self, scenario: EconomicScenario) -> bool:
        """Explicit provenance guard: simulation is never external execution evidence."""
        return scenario.simulated
