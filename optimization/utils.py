import numpy as np
import pandas as pd
from ortools.linear_solver import pywraplp

# Function to convert weight from database fields to metric tons and calculate volume
def convert_weights(data):
    # Calculate total weight per item
    if 'WeightPerUnit' in data.columns and 'TotalUnits' in data.columns and 'BasePackageWeight' in data.columns:
        data['WEIGHT_TONS'] = (
            (pd.to_numeric(data['WeightPerUnit'], errors='coerce') * pd.to_numeric(data['TotalUnits'], errors='coerce')) +
            pd.to_numeric(data['BasePackageWeight'], errors='coerce')
        ) / 1000
    else:
        # Fallback for existing data
        weight_column = 'WEIGHT' if 'WEIGHT' in data.columns else 'Weight'
        data['WEIGHT_TONS'] = pd.to_numeric(data[weight_column], errors='coerce') / 1000

    # Calculate volume
    if 'Lenght' in data.columns and 'Breadth' in data.columns and 'Height' in data.columns:
        data['CBM'] = (
            pd.to_numeric(data['Lenght'], errors='coerce') *
            pd.to_numeric(data['Breadth'], errors='coerce') *
            pd.to_numeric(data['Height'], errors='coerce') / 1000000  # Convert cm³ to m³
        )
    else:
        data['CBM'] = 0

    return data

# Function to calculate the cost based on weight and volume
def calculate_cost(weight, volume, max_weight):
    # Costing based on weight and volume
    if 10 <= weight <= 15 and volume <= max_weight:
        return 103000  # 15 tons
    elif 4.5 <= weight <= 6 and volume <= max_weight:
        return 78000  # 6 tons
    elif 7 <= weight <= 9 and volume <= max_weight:
        return 90000  # 9 tons
    elif 16 <= weight <= 18 and volume <= max_weight:
        return 113000  # 18 tons
    elif 20 <= weight <= 24 and volume <= max_weight:
        return 145000  # 24 tons
    else:
        return 0  # Return 0 for cases that don't match any condition

# Function to optimize package selection based on weight and volume constraints
def optimize_packages(data, carry_capacity, carry_volume):
    required_columns = ['WEIGHT_TONS', 'CBM']
    if not all(col in data.columns for col in required_columns):
        raise ValueError(f"Data must contain columns: {required_columns}")

    solver = pywraplp.Solver.CreateSolver('SCIP')
    if not solver:
        raise ValueError("Solver creation failed. Ensure that OR-Tools is properly installed.")

    num_packages = len(data)
    x = [solver.IntVar(0, 1, f'x[{i}]') for i in range(num_packages)]

    solver.Add(solver.Sum(data.loc[i, 'WEIGHT_TONS'] * x[i] for i in range(num_packages)) <= carry_capacity)
    solver.Add(solver.Sum(data.loc[i, 'CBM'] * x[i] for i in range(num_packages)) <= carry_volume)

    # Maximize total weight and volume (simple objective without priority dates)
    objective = solver.Sum(
        (data.loc[i, 'WEIGHT_TONS'] + data.loc[i, 'CBM']) * x[i]
        for i in range(num_packages)
    )
    solver.Maximize(objective)

    status = solver.Solve()

    if status == pywraplp.Solver.OPTIMAL:
        selected_packages = [i for i in range(num_packages) if x[i].solution_value()]
        total_weight_used = sum(data.loc[i, 'WEIGHT_TONS'] for i in selected_packages)
        total_volume_used = sum(data.loc[i, 'CBM'] for i in selected_packages)
        return selected_packages, total_weight_used, total_volume_used
    else:
        raise ValueError("The solver did not find an optimal solution.")

# Function to create packages based on optimized selection
def create_packages(data, carry_capacity, carry_volume, include_cost=True, max_weight=24):
    packages = []
    unfulfilled_due_to_volume = pd.DataFrame()

    while not data.empty:
        selected_packages, total_weight_used, total_volume_used = optimize_packages(data, carry_capacity, carry_volume)
        if not selected_packages:
            break

        selected_data = data.iloc[selected_packages]
        total_cost = calculate_cost(total_weight_used, total_volume_used, max_weight) if include_cost else None

        if not (
            (4.5 <= total_weight_used <= 6) or
            (7 <= total_weight_used <= 9) or
            (10 <= total_weight_used <= 15) or
            (16 <= total_weight_used <= 18) or
            (20 <= total_weight_used <= 24)
        ) or total_cost == 0:
            unfulfilled_due_to_volume = pd.concat([unfulfilled_due_to_volume, selected_data])
        else:
            # Include all columns from the selected data
            console_df = pd.DataFrame(selected_data)
            console_df.insert(0, 'Console', f"Console {len(packages) + 1}")

            packages.append({
                'Console Data': console_df,
                'Total Weight': round(total_weight_used, 2),
                'Total Volume': round(total_volume_used, 2),
                'Total Cost': total_cost
            })

        data = data.drop(selected_packages).reset_index(drop=True)

    return packages, unfulfilled_due_to_volume

# Recursive function to create packages for all weight classes and split larger ones
def create_packages_recursive(data, weight_range, carry_volume, include_cost, max_weight):
    packages = []
    unfulfilled_packages = pd.DataFrame()

    while not data.empty:
        # Optimize the maximum weight in the range
        selected_packages, total_weight_used, total_volume_used = optimize_packages(data, weight_range[-1], carry_volume)

        if not selected_packages:
            break

        selected_data = data.iloc[selected_packages]
        total_cost = calculate_cost(total_weight_used, total_volume_used, max_weight) if include_cost else None

        # Check if weight can be split
        if total_weight_used == 15:
            packages.append({
                'Job Nos': selected_data['id'].tolist(),
                'Total Weight': 9,
                'Total Volume': total_volume_used * (9 / 15),
                'Total Cost': calculate_cost(9, total_volume_used * (9 / 15), max_weight) if include_cost else None
            })
            packages.append({
                'Job Nos': selected_data['id'].tolist(),
                'Total Weight': 6,
                'Total Volume': total_volume_used * (6 / 15),
                'Total Cost': calculate_cost(6, total_volume_used * (6 / 15), max_weight) if include_cost else None
            })
        elif total_weight_used == 18:
            packages.append({
                'Job Nos': selected_data['id'].tolist(),
                'Total Weight': 15,
                'Total Volume': total_volume_used * (15 / 18),
                'Total Cost': calculate_cost(15, total_volume_used * (15 / 18), max_weight) if include_cost else None
            })
            packages.append({
                'Job Nos': selected_data['id'].tolist(),
                'Total Weight': 6,
                'Total Volume': total_volume_used * (6 / 18),
                'Total Cost': calculate_cost(6, total_volume_used * (6 / 18), max_weight) if include_cost else None
            })
            packages.append({
                'Job Nos': selected_data['id'].tolist(),
                'Total Weight': 9,
                'Total Volume': total_volume_used * (9 / 18),
                'Total Cost': calculate_cost(9, total_volume_used * (9 / 18), max_weight) if include_cost else None
            })
        elif total_weight_used == 24:
            packages.append({
                'Job Nos': selected_data['id'].tolist(),
                'Total Weight': 18,
                'Total Volume': total_volume_used * (18 / 24),
                'Total Cost': calculate_cost(18, total_volume_used * (18 / 24), max_weight) if include_cost else None
            })
            packages.append({
                'Job Nos': selected_data['id'].tolist(),
                'Total Weight': 15,
                'Total Volume': total_volume_used * (15 / 24),
                'Total Cost': calculate_cost(15, total_volume_used * (15 / 24), max_weight) if include_cost else None
            })
            packages.append({
                'Job Nos': selected_data['id'].tolist(),
                'Total Weight': 6,
                'Total Volume': total_volume_used * (6 / 24),
                'Total Cost': calculate_cost(6, total_volume_used * (6 / 24), max_weight) if include_cost else None
            })
            packages.append({
                'Job Nos': selected_data['id'].tolist(),
                'Total Weight': 9,
                'Total Volume': total_volume_used * (9 / 24),
                'Total Cost': calculate_cost(9, total_volume_used * (9 / 24), max_weight) if include_cost else None
            })
        elif not (
            (4.5 <= total_weight_used <= 6) or
            (7 <= total_weight_used <= 9) or
            (10 <= total_weight_used <= 15) or
            (16 <= total_weight_used <= 18) or
            (20 <= total_weight_used <= 24)
        ) or total_cost == 0:
            unfulfilled_packages = pd.concat([unfulfilled_packages, selected_data])
        else:
            packages.append({
                'Job Nos': selected_data['id'].tolist(),
                'Total Weight': total_weight_used,
                'Total Volume': total_volume_used,
                'Total Cost': total_cost
            })

        data = data.drop(selected_packages).reset_index(drop=True)

    # Handle smaller weight classes recursively
    for lower_weight_class in [(4.5, 6), (7, 9), (10, 15), (16, 18), (20, 24)]:
        if lower_weight_class[-1] < weight_range[-1]:
            sub_packages, sub_unfulfilled = create_packages_recursive(data, lower_weight_class, carry_volume, include_cost, max_weight)
            packages.extend(sub_packages)
            unfulfilled_packages = pd.concat([unfulfilled_packages, sub_unfulfilled])

    return packages, unfulfilled_packages

# Function to analyze weight classes and generate a report based on unfulfilled jobs
def analyze_weight_classes(data, container_volume, include_cost=True, max_weight=24):
    fulfilled_files = {}
    unfulfilled_files = []

    weight_class_ranges = {
        '6 Tones': [4.5, 6],
        '9 Tones': [7, 9],
        '15 Tones': [10, 15],
        '18 Tones': [16, 18],
        '24 Tones': [20, 24]
    }

    best_class = None
    best_unfulfilled_count = float('inf')
    best_cost = float('inf')

    for weight_class, weight_range in weight_class_ranges.items():
        packages, unfulfilled_packages = create_packages(data.copy(), weight_range[-1], container_volume, include_cost, max_weight)

        # Store fulfilled packages by weight class
        fulfilled_files[weight_class] = packages
        unfulfilled_count = len(unfulfilled_packages)
        total_unfulfilled_weight = round(unfulfilled_packages['WEIGHT_TONS'].sum(), 2) if not unfulfilled_packages.empty else 0
        total_unfulfilled_cost = calculate_cost(total_unfulfilled_weight, 0, max_weight)

        if unfulfilled_count < best_unfulfilled_count or (unfulfilled_count == best_unfulfilled_count and total_unfulfilled_cost < best_cost):
            best_class = weight_class
            best_unfulfilled_count = unfulfilled_count
            best_cost = total_unfulfilled_cost

        unfulfilled_files.append((weight_class, unfulfilled_packages))

    return fulfilled_files, unfulfilled_files, best_class
