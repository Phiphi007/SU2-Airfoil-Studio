"""Run with ordinary Python 3.9+: python python_api/example.py"""
from autofoil_client import AutoFoilClient

client = AutoFoilClient()
print(client.info())
result = client.run("builtin://naca0012", mode="mesh", parameters={"global_refinement": 0.5})
print("Mesh:", result["files"]["mesh.su2"])
print("Quality:", result["files"]["mesh_quality.json"])
