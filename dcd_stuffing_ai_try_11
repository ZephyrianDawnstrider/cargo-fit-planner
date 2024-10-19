import numpy as np
import pandas as pd
from ortools.linear_solver import pywraplp
import streamlit as st
from datetime import datetime

# Function to load data from a CSV or Excel file with different encodings
def load_data(file, file_type):
    if file_type == 'csv':
        for encoding in ['utf-8', 'latin-1', 'utf-16']:
            try:
                return pd.read_csv(file, encoding=encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError("Failed to load CSV file with supported encodings.")
    elif file_type == 'excel':
        return pd.read_excel(file)
    else:
        raise ValueError("Unsupported file type. Please upload a CSV or Excel file.")

# Function to convert weight from kilograms to metric tons
def convert_weights(data):
    weight_column = 'WEIGHT' if 'WEIGHT' in data.columns else 'Weight'
    data['WEIGHT_TONS'] = data[weight_column] / 1000
    return data

# Function to find the column name that contains 'Job No' or similar
def find_job_no_column(data):
    for col in data.columns:
        if 'job' in col.lower():
            return col
    raise ValueError("No column related to 'Job No' found in the DataFrame.")

# Function to calculate the cost based on weight and volume
def calculate_cost(weight, volume, dcd_upper_limit):
    # Costing based on weight and volume
    if 10 <= weight <= 15 and 45 <= volume <= dcd_upper_limit:
        return 103000  # 15 tons
    elif 4.5 <= weight <= 6 and 45 <= volume <= dcd_upper_limit:
        return 78000  # 6 tons
    elif 7 <= weight <= 9 and 45 <= volume <= dcd_upper_limit:
        return 90000  # 9 tons
    elif 16 <= weight <= 18 and 45 <= volume <= dcd_upper_limit:
        return 113000  # 18 tons
    elif 20 <= weight <= 24 and 45 <= volume <= dcd_upper_limit:
        return 145000  # 24 tons
    else:
        return 0  # Return 0 for cases that don't match any condition

# Function to get volume based on selected volume class
def get_volume_class(volume_class, dcd_upper_limit):
    if volume_class == 'DCD':
        return dcd_upper_limit  # Use the user-defined upper limit for DCD
    else:
        return 0  # Return 0 for unknown volume classes

# Function to calculate days remaining
def calculate_days_remaining(data):
    port_days = {
        # Port data mapping
        'HKG': 27, 'SHA': 29, 'SZX': 23, 'NIN': 26, 'QIN': 34, 'CAN': 22, 
        'TSN': 28, 'XMN': 24, 'DLC': 33, 'FOC': 21, 'ZUH': 20, 'SHEKOU': 25, 
        'YTN': 24, 'NINGDE': 26, 'JIANGYIN': 30, 'CHIWAN': 22, 'ZHANJIANG': 35, 
        'WEIHAI': 32, 'LIANYUNGANG': 31, 'KIX': 21, 'HND': 18, 'NRT': 19, 
        'HIA': 25, 'ICN': 20, 'BUS': 23, 'PKG': 21, 'GMP': 22, 'SIN': 15, 
        'BKK': 30, 'KUL': 28, 'JKT': 26, 'MAN': 32
    }

    current_date = datetime.now().date()
    data['ETD'] = pd.to_datetime(data['ETD'], errors='coerce')
    data['DAYS_REMAINING'] = data.apply(lambda row: port_days.get(row['POL'], 0) - (current_date - row['ETD'].date()).days if pd.notnull(row['ETD']) else 0, axis=1)
    return data

# Function to optimize package selection based on weight and volume constraints
def optimize_packages(data, carry_capacity, carry_volume):
    required_columns = ['WEIGHT_TONS', 'CBM', 'DAYS_REMAINING']
    if not all(col in data.columns for col in required_columns):
        st.error(f"Data must contain columns: {required_columns}")
        return [], 0, 0

    solver = pywraplp.Solver.CreateSolver('SCIP')
    if not solver:
        st.error("Solver creation failed. Ensure that OR-Tools is properly installed.")
        return [], 0, 0

    num_packages = len(data)
    x = [solver.IntVar(0, 1, f'x[{i}]') for i in range(num_packages)]

    solver.Add(solver.Sum(data.loc[i, 'WEIGHT_TONS'] * x[i] for i in range(num_packages)) <= carry_capacity)
    solver.Add(solver.Sum(data.loc[i, 'CBM'] * x[i] for i in range(num_packages)) <= carry_volume)

    objective = solver.Sum(
        (data.loc[i, 'WEIGHT_TONS'] + data.loc[i, 'CBM']) / max(1, data.loc[i, 'DAYS_REMAINING']) * x[i]
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
        st.error("The solver did not find an optimal solution.")
        return [], 0, 0

# Function to create packages based on optimized selection
def create_packages(data, carry_capacity, carry_volume, include_cost=True, dcd_upper_limit=58):
    packages = []
    unfulfilled_due_to_volume = pd.DataFrame()

    while not data.empty:
        selected_packages, total_weight_used, total_volume_used = optimize_packages(data, carry_capacity, carry_volume)
        if not selected_packages:
            break

        selected_data = data.iloc[selected_packages]
        job_nos = selected_data[find_job_no_column(data)].tolist()
        days_remaining = selected_data['DAYS_REMAINING'].tolist()
        total_cost = calculate_cost(total_weight_used, total_volume_used, dcd_upper_limit) if include_cost else None

        if (not (
                (4.5 <= total_weight_used <= 6) or
                (7 <= total_weight_used <= 9) or
                (10 <= total_weight_used <= 15) or
                (16 <= total_weight_used <= 18) or
                (20 <= total_weight_used <= 24)
            )) or total_cost == 0:
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

# Function to analyze weight classes and generate a report based on unfulfilled jobs
def analyze_weight_classes(data, dcd_upper_limit, include_cost=True):
    fulfilled_files = {}
    unfulfilled_files = []

    weight_class_ranges = {
        '6 Tones': [4.5, 6],
        '9 Tones': [7, 9],
        '15 Tones': [10, 15],
        '18 Tones': [16, 18],
        '24 Tones': [20, 24]
    }

    volume_class = get_volume_class('DCD', dcd_upper_limit)  # Assuming the user selects DCD

    best_class = None
    best_unfulfilled_count = float('inf')
    best_cost = float('inf')

    for weight_class, weight_range in weight_class_ranges.items():
        packages, unfulfilled_packages = create_packages(data.copy(), weight_range[-1], volume_class, include_cost, dcd_upper_limit)

        # Store fulfilled packages by weight class
        fulfilled_files[weight_class] = packages
        unfulfilled_count = len(unfulfilled_packages)
        total_unfulfilled_weight = round(unfulfilled_packages['WEIGHT_TONS'].sum(), 2) if not unfulfilled_packages.empty else 0
        total_unfulfilled_cost = calculate_cost(total_unfulfilled_weight, 0, dcd_upper_limit)  # Fixed line

        if unfulfilled_count < best_unfulfilled_count or (unfulfilled_count == best_unfulfilled_count and total_unfulfilled_cost < best_cost):
            best_class = weight_class
            best_unfulfilled_count = unfulfilled_count
            best_cost = total_unfulfilled_cost

        unfulfilled_files.append((weight_class, unfulfilled_packages))

    return fulfilled_files, unfulfilled_files, best_class

# Main Streamlit App
def main():
    st.title("Truck Shipment Optimization Tool")

    uploaded_file = st.file_uploader("Upload your data file (CSV or Excel)", type=['csv', 'xlsx'])

    if uploaded_file:
        file_type = 'csv' if uploaded_file.name.endswith('.csv') else 'excel'
        data = load_data(uploaded_file, file_type)
        data = convert_weights(data)
        data = calculate_days_remaining(data)

        selected_volume_class = st.selectbox("Select Volume Class", ['DCD', 'Other'])
        dcd_upper_limit = st.number_input("Enter DCD Upper Limit", min_value=1.0, value=58.0, step=1.0)
        include_cost = st.checkbox("Include Cost", value=True)

        if st.button("Generate Report"):
            fulfilled_files, unfulfilled_files, best_class = analyze_weight_classes(data, dcd_upper_limit, include_cost)

            # Initialize variables to calculate the total cost of the best class
            total_cost_best_class = 0
            best_weight_class_packages = []

            if fulfilled_files:
                st.write("### Consoles for Best Weight Class:")
                
                # Check the fulfilled files to see if they match the best class
                for weight_class, packages in fulfilled_files.items():
                    # If the current weight class matches the best class, add the packages
                    if weight_class == best_class:
                        best_weight_class_packages.extend(packages)
                        # Calculate the total cost for the best weight class
                        for pkg in packages:
                            total_cost_best_class += pkg['Total Cost'] if pkg['Total Cost'] is not None else 0

                # Display the best weight class packages
                if best_weight_class_packages:
                    for best_package in best_weight_class_packages:
                        st.dataframe(best_package['Console Data'])
                        st.write(f"**Total Weight Used:** {best_package['Total Weight']} tons")
                        st.write(f"**Total Volume Used:** {best_package['Total Volume']} CBM")
                        st.write(f"**Total Cost:** {best_package['Total Cost']}")

                # Display unfulfilled packages for the best class
                st.write("### Unfulfilled Packages for Best Weight Class:")
                for weight_class, unfulfilled in unfulfilled_files:
                    if weight_class == best_class:
                        st.write(f"#### Unfulfilled Packages for {weight_class}:")
                        st.dataframe(unfulfilled)

            # Summary report
            st.write("### Summary Report:")
            st.write(f"**Best Weight Class:** {best_class}")
            st.write(f"**Total Cost for Best Weight Class:** {total_cost_best_class} (if applicable)")
            st.write(f"**Total Unfulfilled Count:** {len(unfulfilled_files)}")

            # Add an expander for fulfilled consoles
            with st.expander("View All Fulfilled Consoles"):
                for idx, (weight_class, packages) in enumerate(fulfilled_files.items()):
                    st.write(f"#### Package {idx + 1} for Weight Class: {weight_class}")
                    for pkg in packages:
                        st.dataframe(pkg['Console Data'])
                        st.write(f"**Total Weight Used:** {pkg['Total Weight']} tons")
                        st.write(f"**Total Volume Used:** {pkg['Total Volume']} CBM")
                        st.write(f"**Total Cost:** {pkg['Total Cost']}")

            # Add an expander for unfulfilled packages
            with st.expander("View Unfulfilled Packages"):
                for weight_class, unfulfilled in unfulfilled_files:
                    st.write(f"#### {weight_class} Unfulfilled Packages")
                    st.dataframe(unfulfilled)

            # Comparative report
            st.write("### Comparative Report")
            comparative_data = []

            for weight_class, packages in fulfilled_files.items():
                total_weight = sum(pkg['Total Weight'] for pkg in packages)
                total_volume = sum(pkg['Total Volume'] for pkg in packages)
                total_cost = sum(pkg['Total Cost'] if pkg['Total Cost'] is not None else 0 for pkg in packages)
                
                # Calculate total unfulfilled weight and volume for this weight class
                unfulfilled_weight = 0
                unfulfilled_volume = 0
                for wc, unfulfilled in unfulfilled_files:
                    if wc == weight_class:
                        unfulfilled_weight = unfulfilled['WEIGHT_TONS'].sum() if not unfulfilled.empty else 0
                        unfulfilled_volume = unfulfilled['CBM'].sum() if not unfulfilled.empty else 0
                
                comparative_data.append({
                    'Weight Class': weight_class,
                    'Total Consoles Made': len(packages),
                    'Total Weight Used (tons)': total_weight,
                    'Total Volume Used (CBM)': total_volume,
                    'Total Unfulfilled Weight (tons)': unfulfilled_weight,
                    'Total Unfulfilled Volume (CBM)': unfulfilled_volume,
                    'Total Cost': total_cost
                })

            # Create a DataFrame for the comparative report
            comparative_df = pd.DataFrame(comparative_data)
            st.dataframe(comparative_df)

if __name__ == "__main__":
    main()
