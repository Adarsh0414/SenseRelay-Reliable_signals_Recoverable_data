# Dashboard layout fix

## Symptom
The Overview tab occupied the expected dashboard width, while Sessions, Processing results, Data integrity, and Host resources appeared shifted inward or narrowed.

## Root cause
The dashboard body is a flex child with auto inline margins and an auto width. In a column flex layout, that combination can let its used width depend on intrinsic content sizing. Different tab content then caused the grid and sidebar to appear at different horizontal positions. The main grid item also had its own width, max-width, and auto margins, even though the parent grid already controls its available width.

## Fix
- Give `.dashboard-body` an explicit `width: 100%` and `min-width: 0`, retain the 1600px maximum width, and use `box-sizing: border-box`.
- Let `.dashboard-main` fill the second grid track instead of applying a second max-width and auto-centering rule.
- Keep the existing responsive grid breakpoints, sidebar width, padding system, fixed viewport shell, and independent content scrolling.

## Verification
- Python backend regression suite: 31 tests passed in the available local environment after the CSS change.
- Frontend browser rendering still needs to be checked in the user's local Vite session. Verify Overview, Sessions, Processing results, Data integrity, Host resources, and Settings at the same browser size. The sidebar should stay in one horizontal position and content should begin at the same grid boundary for every tab.
