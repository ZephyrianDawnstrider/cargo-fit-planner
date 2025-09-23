# TODO: Implement Mixed Container Stuffing Optimization

## Step 1: Add mixed_bin_packing function to utils.py
- [x] Create a new function `mixed_bin_packing` that takes cargo data, available containers, and returns list of used containers with packed items.
- [x] Use heuristic: sort containers by volume descending for selection.
- [x] Greedily pack: while cargo remains, select the largest container type that can accommodate remaining cargo total, pack subset into it using optimize_packages, create 3D model, handle unplaced.

## Step 2: Modify views.py upload_view
- [x] Replace the if all_selected and else blocks with a single mixed scenario.
- [x] Call mixed_bin_packing with all available containers for the category.
- [x] Create one scenario dict with the results.

## Step 3: Update results.html if needed
- [x] Ensure it displays the single mixed scenario correctly (should work as is).

## Step 4: Test the implementation
- [x] Run the app, select cargo and containers, verify it creates one scenario with mixed containers minimizing number.
- [x] Check 3D models and tables.

## Step 5: Handle edge cases
- [x] If no containers can fit remaining, stop and show remaining.
- [x] Ensure logging and error handling.
