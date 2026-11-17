# Contributing

## Development setup

Use Windows with Python 3.11 or 3.12. Run `Setup_Windows.bat`, or create `.venv`
and install `requirements.txt` manually. SU2 is only required for an actual CFD
run; it must be installed separately and expose `SU2_CFD.exe` on `PATH`.

Run the regression suite before submitting a change:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Mesh changes

Changes to the grid generator must preserve the invariants in
`docs/ARCHITECTURE.md`: sharp trailing edge, continuous leading edge, conformal
C-H blocks, quadrilateral-only volume cells, positive area and the documented
quality gates. Add or update tests whenever an invariant or public parameter is
changed.

Generated results, virtual environments, runtime caches and temporary test data
must not be committed.
