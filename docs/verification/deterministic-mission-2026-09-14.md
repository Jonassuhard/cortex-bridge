# API integration fixture — 14 September 2026

Historical test invocation, with the private interpreter path replaced by a
portable placeholder (set PYTHON to the installed project interpreter):

```text
"$PYTHON" -m unittest -v \
  tests.test_missions_api.MissionsApiTestCase.test_02_full_mission_via_api
```

Result:

```text
test_02_full_mission_via_api ... ok
Ran 1 test in 3.040s
OK
```

The scenario creates a mission through the API, executes a deterministic
`write_file` action, verifies the exact file content, receives a terminal
`COMPLETE` decision and closes the mission. The assistant decisions are scripted
by the test fixture. This demonstrates API integration and a local file write,
not a live supervisor/operator mission or external-model execution.

It is deliberately not labelled as Luna, Freebuff or ChatGPT provider
acceptance. Those channels remain separate release gates.
