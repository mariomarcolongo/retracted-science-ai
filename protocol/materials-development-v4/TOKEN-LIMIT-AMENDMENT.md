# Kimi completion-budget amendment

16 November 2026, before the amended calls. Kimi's six-item v4 batch completed
four usable question strings but returned empty final content with a length stop
for 10D131 and 3E1E72 at max_tokens 4000. Those two responses are operationally
incomplete, not usable questions, and remain preserved with their usage/reasoning.

Increase max_tokens to 16000 for a new complete SIX-ITEM Kimi drafting batch,
holding prompt, original source inputs, model/provider, temperature and top_p
unchanged. Do not combine the four earlier completions with two new outputs or
choose the preferred text item by item. The complete new configuration is the
candidate method; the earlier batch documents the insufficiency of the 4000-token
allowance for this endpoint's provider-default reasoning. No prompt is revised
using the returned reasoning. Other unspecified settings remain omitted.

This is a disclosed operational configuration amendment, not an unlogged retry of
successful content. Use a $1 scheduling guard within the preparation target.
Keep the same scientific rubric and stop if the new batch remains incomplete.
