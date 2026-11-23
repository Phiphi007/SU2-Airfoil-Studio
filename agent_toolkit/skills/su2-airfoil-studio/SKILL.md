# SU2 Airfoil Studio agent workflow

Use the repository's `agent_toolkit/mcp_server.py` through a local stdio MCP client. The tool server is an adapter to `portable_api.py`; it controls the same numerical backend as the Qt6 application, not the GUI widgets.

1. Call `studio_info` to discover the solver and supported modes. If SU2 is missing, mesh and report can still be used; a CFD solve needs a configured `SU2_CFD` executable.
2. Call `studio_schema` and use only listed parameter names. Set a new absolute `output_dir` for every mesh or solve operation.
3. Call `studio_run` with `mode=mesh` and inspect `files`, cell counts and logs. Then call it with `mode=solve` for a CFD case and check `ok`, `status`, residuals, and returned result files.
4. Use `mode=report` only on an existing completed case with `history.csv` and `surface_flow.csv`.
5. For discrete-adjoint optimization, first complete a direct case whose `residual_target_met` is true. Then call `studio_run` with `mode=optimize`, its `case_dir`, a new `output_dir`, a method (`cst`, `bce`, `hybrid`, or `relay`), and a positive step count. Inspect accepted steps and geometry/force history. A successful process exit or a rejected trial does not imply aerodynamic improvement. GUI widget control is still an open feature-parity milestone.

Use the project's private Python runtime when available: `build/studio-app/runtime/python/bin/python agent_toolkit/mcp_server.py`. On Windows, use the corresponding `Scripts/python.exe`. Never send prose to stdout from the MCP process.
