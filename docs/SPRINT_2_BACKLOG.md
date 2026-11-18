# Sprint 2 Backlog — Restaurant Order Agent

> **To the team:** the technical rows below are filled in from the code, tests, and evaluation. Everything in `[square brackets]` is a fact about how we worked. Fill it in with what really happened, and do not keep a placeholder as if it were true.

## Sprint Goal

**"A customer can order in a Streamlit page: the assistant prepares a draft with the Sprint 1 tools, and the customer sees, cancels, or confirms their own drafts through an MCP server."**

- **Sprint:** 2 (`[start date]` to `[end date]`)

## Roles

| Role | Person | What this person did in this sprint |
|---|---|---|
| Product Owner | `[name]` | `[one prioritization or clarification decision, for example: PBI-11 exposes three new order tools instead of the six existing tools]` |
| Scrum Master | `[name]` | `[how this person made a blocker visible or removed it, for example: the Groq output-token limit]` |
| Developers | `[all names]` | `[who built what: see the owner column below]` |

### How technical work was shared

`[Describe the real split. A possible boundary: one person builds src/orders.py, the MCP server, and the MCP client; one person builds app.py, src/app_logic.py, and the page tests; one person runs the evaluation in Groq and Colab and writes the documents.]`

## Selected items and tasks

| Product Backlog item | Implementation tasks | Owner(s) | Estimate | Status | Acceptance evidence |
|---|---|---|---|---|---|
| Sprint 1 baseline | Keep the six tools, the database, and the inventory API working; run E-01 to E-08 again | `[names]` | `[ ]` | Done | Groq: 12 Pass, 4 Partial, 0 Fail in 16 runs (`SPRINT_2_EVALUATION.md`). The 154 Sprint 1 unit tests still pass, 2 of them changed on purpose. |
| PBI-21 | Retry a refused Groq tool call with a note that names the correct tools; show a friendly error instead of raw error text | `[names]` | `[ ]` | **Partial** | `test_retry_adds_a_note_with_the_tool_names_and_does_not_keep_it`, `test_model_error_gives_an_answer_instead_of_a_crash`. No refused call happened in the 22 Groq runs, so the retry has no evidence from a real model. |
| PBI-12 | Add sessions to drafts (`session_id`); write the list, cancel, and confirm rules in `src/orders.py`; check stock again before a confirmation | `[names]` | `[ ]` | Done | `tests/test_orders.py` (23 tests): other sessions' drafts are not found; a refused confirmation changes nothing. |
| PBI-11 | Implement the MCP server with `list_drafts`, `cancel_draft`, `confirm_draft` | `[names]` | `[ ]` | Done | `src/mcp_server/`. `tests/test_mcp_server.py`; `test_server_offers_its_three_tools` lists the tools through a real connection. |
| PBI-11 | Implement the MCP client (stdio) and connect it to the assistant as the tools `list_drafts` and `cancel_draft` | `[names]` | `[ ]` | Done | `src/mcp_client/`, `src/agent_tools.py`. E-09: the trace shows `list_drafts` and `cancel_draft` with path `mcp`, and the draft is `cancelled` in SQLite. E-10 and E-11 for no match and server failure. |
| PBI-10 | Build the Streamlit page: chat, tool calls, cart, Confirm and Cancel, outage switch; keep the logic in `src/app_logic.py` | `[names]` | `[ ]` | Done | `streamlit run app.py`. G-01 by hand in a browser; `tests/test_app.py` (9 tests) and `tests/test_app_logic.py` (18 tests). |
| PBI-14 | Add unit tests for the new functions; save the test run | `[names]` | `[ ]` | Done | 239 tests pass. `docs/SPRINT_2_UNIT_TESTS.md`, `docs/test_results/sprint2_unit_tests.txt`. |
| PBI-23 | Extend the evaluation runner with MCP scenarios; run Groq; run one scenario in Streamlit | `[names]` | `[ ]` | Done | `src/evaluation.py`; `docs/eval_results/groq_2026-11-15_0004.json`; `SPRINT_2_EVALUATION.md`. |
| PBI-23 | Run the evaluation with local Qwen in Colab and fill in the comparison | Person C | `[ ]` | Done | `docs/eval_results/local_2026-11-18_1240.json`: 8 Pass, 3 Partial, 0 Fail. Comparison table in `SPRINT_2_EVALUATION.md`. A second Groq run in Colab (`groq_2026-11-18_1216.json`) gave the same results as on 2026-11-15. |
| PBI-22 | Decide the E-03 and E-05 answer criteria | `[names]` | `[ ]` | **To do** | Open. |
| — | README, tool contract, Product Vision, Product Backlog | `[names]` | `[ ]` | Done | Files in the repository. `docs/CONTRACT.md` still has the status "draft, waiting for review". |
| — | Sprint 2 Review, retrospective, and presentation slides | `[names]` | `[ ]` | **To do** | `docs/SPRINT_2_REVIEW.md` has the technical parts; the team parts are open. |

## Definition of Done

An item is Done when:

1. It runs from the README steps.
2. It meets its acceptance criterion in `PRODUCT_BACKLOG.md`.
3. It has evidence named in this file: a unit test, an evaluation scenario, or both.
4. The Sprint 1 scenarios still work, or a regression is recorded.
5. No credentials or personal data are in the repository.

## Risks and blockers

| Risk or blocker | Status | What we did or will do |
|---|---|---|
| Groq's free tier refuses requests that may write more than 1000 tokens, and limits output per minute | Found on 2026-11-14: the first evaluation run failed in 21 of 22 runs with HTTP 429 | Each reply is limited to 800 tokens, with more retries. A request can now take up to a minute. For the review: rehearse, and keep the recorded results as a fallback. |
| The corrective retry has no evidence from a real model | Open | Keep PBI-21 as Partial. A refused call must be seen and fixed in a real run before it is Done. |
| Local Qwen needs a Colab GPU | Handled | Person C ran it on a Colab T4 GPU on 2026-11-18. |
| `mcp` 2.x changed its API | Handled | `requirements.txt` pins `mcp>=1.12,<2`. |
| The code ran only on Windows with Python 3.14 | Handled | On 2026-11-18 Person C ran `notebooks/demo.ipynb` in Colab (Linux, Python 3.13) from the README steps: setup, Demo A, Demo B, Demo C (MCP), the Groq evaluation, and local mode all ran without errors. |
