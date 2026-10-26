# Development review and reflection notes

For each checkpoint PR, prioritize failure analysis over a long success summary.
This is the user's requested development/reporting convention.

Record each observed development or test failure with:

1. The triggering scenario and expected behavior.
2. What actually happened, with the exception or observable result.
3. The cause established by evidence; distinguish a diagnosis from an assumption.
4. The change made and why it addresses that cause.
5. Verification after the change and remaining limitations.

Distinguish deliberate fault injection from unexpected defects. Keep success
counts brief. Link the PR to the repository's checkpoint report so the reflection
can be composed from the PR history. Do not claim a fix is verified until its
relevant rerun has completed.
