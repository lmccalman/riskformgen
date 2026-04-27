# diff fixtures

Each subfolder is one scenario:

```
<scenario>/
  prev_q.json     # prior questionnaire (or absent if "first record" case)
  prev_a.json     # prior assessment (or absent)
  cur_q.json      # current questionnaire
  cur_a.json      # current assessment (or absent)
  expected.json   # asdict(diff_pair(prev_q, prev_a, cur_q, cur_a))
```

`tests/test_diff.py` walks every subfolder, runs `diff.diff_pair` over the
inputs, and asserts the result matches `expected.json`. The same fixtures
are loaded by `tests/test_js_behaviour.py` to drive the assessment
factory's JS diff and assert it produces an equivalent shape — the parity
contract that keeps live and registry-rendered diffs aligned.

When adding a fixture, keep it minimal: focus on one kind of change so a
failure points unambiguously at what regressed.
