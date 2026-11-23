# Cessna 172 inspired airfoil study — validation plan

This is a **planned design study**, not a claim about certified Cessna geometry, performance, or an approved modification. It will become a chapter in the English PDF user guide only after the workflow and results pass validation.

## Aircraft context and traceable inputs

The current [Textron Aviation Cessna Skyhawk specifications](https://cessna.txtav.com/en/piston/cessna-skyhawk?values=Skyhawk) list wingspan 11.00 m, wing area 16.17 m², maximum takeoff mass 1,157 kg, and maximum cruise speed 124 ktas (230 km/h). These are aircraft-level values for context. The exact wing section, twist, flap geometry, and local section operating conditions are **not established by that page**. The study must not label a generated NACA 2412 section as the certified Cessna 172 airfoil without a primary type-design source.

For a transparent sea-level demonstration, 230 km/h is about 63.9 m/s. Taking illustrative air density 1.225 kg/m³ and maximum mass 1,157 kg gives an aircraft lift coefficient estimate

\[
C_L \approx \frac{mg}{\tfrac12\rho V^2S} \approx 0.28.
\]

This estimate is a whole-aircraft coefficient under stated assumptions. It does **not** directly prescribe the two-dimensional section target because induced effects, spanwise loading, twist, fuselage lift, and trim are absent from a 2-D calculation. A section target must be chosen and justified separately. Use an analytic NACA 2412 as a *candidate baseline* and NACA 4412 as a higher-camber comparison, not as claims about the actual production wing.

## Proposed reproducible workflow

1. Record the installed app, Qt, Gmsh, and SU2 versions, the baseline airfoil source, fluid properties, Mach, Reynolds number, and angle of attack. State whether the condition represents cruise, climb, or low-speed operation.
2. Generate a coarse and refined mesh for each candidate. Inspect near-wall cells, quality, trailing-edge wake, and outer boundary. Save the mesh and configuration with the case.
3. Run direct SU2 cases at multiple angles of attack. Require residual and force-history stability and compare lift, drag, moment, and surface pressure. Repeat on a refined mesh to estimate discretization sensitivity.
4. Choose a converged operating point and run CST, BCE, hybrid, and relay adjoint studies under the same objective and geometry constraints. Record rejected as well as accepted trials. Compare optimized geometry, objective history, and off-design cases.
5. Reopen the cases in the packaged Qt desktop and export a report with figures, numeric tables, assumptions, source links, and the full limitations of 2-D CFD. A 3-D wing or aircraft analysis would be a separate validation step before any aircraft-level conclusion.

## Current status

The analytic NACA 2412 integration case and one CST adjoint probe ran through the numerical executables. Their direct baseline did not converge; the probe accepted no geometry changes. The NACA 4412 candidate has passed mesh generation only. None of these outputs are ready for the final aircraft-design report.
