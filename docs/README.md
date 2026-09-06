# Backend documentation

The deterministic navigation core and a substantial offline road-context layer
are implemented. This directory records the architecture, decisions, evidence,
and remaining promotion gates; it must not be read as evidence that every
proposed runtime feature is already enabled.

- `architecture.md` describes the implemented deterministic data flow and the
  future, causally constrained road-context insertion point.
- `decisions.md` records selected technologies and genuinely unresolved choices.
- `validation_plan.md` separates implemented unit coverage from remaining
  experiment, replay, and deployment evidence.
- `road_context_model.md` is the detailed methodology, implementation boundary,
  and deployment-gate document for the in-progress road-context engine.
- `backend_flutter_integration.md` documents current Python entry points,
  replay commands, and the proposed—not implemented—mobile transport contract.
