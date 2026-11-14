# AI-tool usage disclosure

Per the hackathon rules on AI/LLM assistance: AI tooling (Instinct, an AI
assistant) was used materially for research, design, code, tests, documentation
and demo preparation of this project. All quantum-circuit choices, statistics
and claims were reviewed against primary sources (the official problem
statements, the hackathon rulebook and qniverse.in documentation) and are
covered by the automated test suite; the team can explain every part of the
implementation.

Key design points and their human-verifiable basis:

- Batching rounds as independent qubits with `shots=1`: follows from the
  documented one-circuit-per-job, aggregate-counts execution model.
- Coherent Eve (CNOT to ancilla): the standard purified form of
  intercept-resend; statistics verified empirically in the test suite.
- 11% detection threshold: the textbook BB84 bound, used as an educational
  flag only.
