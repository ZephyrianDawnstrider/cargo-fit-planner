import numpy as np
import pandas as pd
from ortools.linear_solver import pywraplp
import streamlit as st
from datetime import datetime

st. set_page_config(layout="wide") 

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
        # Hong Kong
        'HKG': 27, 'HONGKONG': 27, 'HONG_KONG': 27, 'hkg': 27, 'hongkong': 27, 'hong_kong': 27, 
        'Hkg': 27, 'Hongkong': 27, 'Hong_Kong': 27, 'hong kong': 27, 'Hong Kong': 27,

        # Shanghai
        'SHA': 29, 'SHANGHAI': 29, 'SHANG_HAI': 29, 'sha': 29, 'shanghai': 29, 'shang_hai': 29, 
        'Sha': 29, 'Shanghai': 29, 'Shang_Hai': 29,

        # Shenzhen
        'SZX': 23, 'SHZ': 23, 'SHENZHEN': 23, 'SHEN_ZHEN': 23, 'szx': 23, 'shz': 23, 
        'shenzhen': 23, 'shen_zhen': 23, 'Szx': 23, 'Shz': 23, 'Shenzhen': 23, 'Shen_Zhen': 23,

        # Ningbo
        'NIN': 26, 'NINGBO': 26, 'NING_BO': 26, 'nin': 26, 'ningbo': 26, 'ning_bo': 26, 
        'Nin': 26, 'Ningbo': 26, 'Ning_Bo': 26,

        # Qingdao
        'QIN': 34, 'QINGDAO': 34, 'QING_DAO': 34, 'qin': 34, 'qingdao': 34, 'qing_dao': 34, 
        'Qin': 34, 'Qingdao': 34, 'Qing_Dao': 34,

        # Guangzhou
        'CAN': 22, 'GUANGZHOU': 22, 'GUANG_ZHOU': 22, 'can': 22, 'guangzhou': 22, 'guang_zhou': 22, 
        'Can': 22, 'Guangzhou': 22, 'Guang_Zhou': 22,

        # Tianjin
        'TSN': 28, 'TIANJIN': 28, 'TIAN_JIN': 28, 'tsn': 28, 'tianjin': 28, 'tian_jin': 28, 
        'Tsn': 28, 'Tianjin': 28, 'Tian_Jin': 28,

        # Xiamen
        'XMN': 24, 'XIAMEN': 24, 'XIA_MEN': 24, 'xmn': 24, 'xiamen': 24, 'xia_men': 24, 
        'Xmn': 24, 'Xiamen': 24, 'Xia_Men': 24,

        # Dalian
        'DLC': 33, 'DALIAN': 33, 'DA_LIAN': 33, 'dlc': 33, 'dalian': 33, 'da_lian': 33, 
        'Dlc': 33, 'Dalian': 33, 'Da_Lian': 33,

        # Fuzhou
        'FOC': 21, 'FUZHOU': 21, 'FU_ZHOU': 21, 'foc': 21, 'fuzhou': 21, 'fu_zhou': 21, 
        'Foc': 21, 'Fuzhou': 21, 'Fu_Zhou': 21,

        # Zhuhai
        'ZUH': 20, 'ZHUHAI': 20, 'ZHU_HAI': 20, 'zuh': 20, 'zhuhai': 20, 'zhu_hai': 20, 
        'Zuh': 20, 'Zhuhai': 20, 'Zhu_Hai': 20,

        # Shekou
        'SHEKOU': 25, 'SHE_KOU': 25, 'Shekou': 25, 'She_Kou': 25, 'shekou': 25, 'she_kou': 25,

        # Yantian
        'YTN': 24, 'YANTIAN': 24, 'YAN_TIAN': 24, 'ytn': 24, 'yantian': 24, 'yan_tian': 24, 
        'Ytn': 24, 'Yantian': 24, 'Yan_Tian': 24,

        # Other Chinese Minor Ports
        'NINGDE': 26, 'NING_DE': 26, 'ningde': 26, 'ning_de': 26, 'Ningde': 26, 'Ning_De': 26,
        'JIANGYIN': 30, 'JIANG_YIN': 30, 'jiangyin': 30, 'jiang_yin': 30, 'Jiangyin': 30, 'Jiang_Yin': 30,
        'CHIWAN': 22, 'CHI_WAN': 22, 'chiwan': 22, 'chi_wan': 22, 'Chiwam': 22, 'Chi_Wan': 22,
        'ZHANJIANG': 35, 'ZHAN_JIANG': 35, 'zhanjiang': 35, 'zhan_jiang': 35, 'Zhanjiang': 35, 'Zhan_Jiang': 35,
        'WEIHAI': 32, 'WEI_HAI': 32, 'weihai': 32, 'wei_hai': 32, 'Weihai': 32, 'Wei_Hai': 32,
        'LIANYUNGANG': 31, 'LIAN_YUN_GANG': 31, 'lianyungang': 31, 'lian_yun_gang': 31, 
        'Lianyungang': 31, 'Lian_Yun_Gang': 31,

        # Major Japanese Ports
        'KIX': 21, 'OSAKA': 21, 'KIX_OSAKA': 21, 'kix': 21, 'osaka': 21, 'kix_osaka': 21, 
        'Kix': 21, 'Osaka': 21, 'KIX_OSAKA': 21, 
        'HND': 18, 'TOKYO': 18, 'HND_TOKYO': 18, 'hnd': 18, 'tokyo': 18, 'hnd_tokyo': 18, 
        'Hnd': 18, 'Tokyo': 18, 'HND_TOKYO': 18,
        'NRT': 19, 'NARITA': 19, 'NRT_NARITA': 19, 'nrt': 19, 'narita': 19, 'nrt_narita': 19, 
        'Nrt': 19, 'Narita': 19, 'NRT_NARITA': 19,
        'HIA': 25, 'HIROSHIMA': 25, 'HIA_HIROSHIMA': 25, 'hia': 25, 'hiroshima': 25, 'hia_hiroshima': 25,
        'Hia': 25, 'Hiroshima': 25, 'HIA_HIROSHIMA': 25,

        # Major South Korean Ports  
        'ICN': 20, 'SEOUL': 20, 'ICN_SEOUL': 20, 'icn': 20, 'seoul': 20, 'icn_seoul': 20, 
        'Icn': 20, 'Seoul': 20, 'ICN_SEOUL': 20, 
        'BUS': 23, 'BUSAN': 23, 'BUS_BUSAN': 23, 'bus': 23, 'busan': 23, 'bus_bus': 23, 
        'Bus': 23, 'Busan': 23, 'BUS_BUSAN': 23,
        'PKG': 21, 'PUSAN': 21, 'PKG_PUSAN': 21, 'pkg': 21, 'pusan': 21, 'pkg_pusan': 21, 
        'Pkg': 21, 'Pusan': 21, 'PKG_PUSAN': 21,
        'GMP': 22, 'GIMPO': 22, 'GMP_GIMPO': 22, 'gmp': 22, 'gimpo': 22, 'gmp_gimpo': 22, 
        'Gmp': 22, 'Gimpo': 22, 'GMP_GIMPO': 22,

        # Major Southeast Asian Ports
        'SIN': 15, 'SINGAPORE': 15, 'SIN_SINGAPORE': 15, 'sin': 15, 'singapore': 15, 'sin_singapore': 15, 
        'Sin': 15, 'Singapore': 15, 'SIN_SINGAPORE': 15,
        'BKK': 30, 'BANGKOK': 30, 'BKK_BANGKOK': 30, 'bkk': 30, 'bangkok': 30, 'bkk_bangkok': 30, 
        'Bkk': 30, 'Bangkok': 30, 'BKK_BANGKOK': 30,
        'KUL': 28, 'KUALA LUMPUR': 28, 'KUL_KUALA_LUMPUR': 28, 'kul': 28, 'kuala_lumpur': 28, 'kul_kuala_lumpur': 28, 
        'Kul': 28, 'Kuala_Lumpur': 28, 'KUL_KUALA_LUMPUR': 28,
        'JKT': 26, 'JAKARTA': 26, 'JKT_JAKARTA': 26, 'jkt': 26, 'jakarta': 26, 'jkt_jakarta': 26, 
        'Jkt': 26, 'Jakarta': 26, 'JKT_JAKARTA': 26,
        'MAN': 32, 'MANILA': 32, 'MAN_MANILA': 32, 'man': 32, 'manila': 32, 'man_manila': 32, 
        'Man': 32, 'Manila': 32, 'MAN_MANILA': 32
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

    solver = pywraplp.Solver.CreateSolver('SCIP') #SCIP is currently one of the fastest non-commercial solvers for mixed integer programming (MIP) and mixed integer nonlinear programming (MINLP)
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

# Recursive function to create packages for all weight classes and split larger ones
def create_packages_recursive(data, weight_range, carry_volume, include_cost, dcd_upper_limit):
    packages = []
    unfulfilled_packages = pd.DataFrame()

    while not data.empty:
        # Optimize the maximum weight in the range
        selected_packages, total_weight_used, total_volume_used = optimize_packages(data, weight_range[-1], carry_volume)

        if not selected_packages:
            break

        selected_data = data.iloc[selected_packages]
        job_nos = selected_data[find_job_no_column(data)].tolist()
        total_cost = calculate_cost(total_weight_used, total_volume_used, dcd_upper_limit) if include_cost else None

        # Check if weight can be split
        if total_weight_used == 15:
            packages.append({
                'Job Nos': job_nos,
                'Total Weight': 9,
                'Total Volume': total_volume_used * (9 / 15),  # Split volume proportionally
                'Total Cost': calculate_cost(9, total_volume_used * (9 / 15), dcd_upper_limit) if include_cost else None
            })
            packages.append({
                'Job Nos': job_nos,
                'Total Weight': 6,
                'Total Volume': total_volume_used * (6 / 15),  # Split volume proportionally
                'Total Cost': calculate_cost(6, total_volume_used * (6 / 15), dcd_upper_limit) if include_cost else None
            })
        elif total_weight_used == 18:
            packages.append({
                'Job Nos': job_nos,
                'Total Weight': 15,
                'Total Volume': total_volume_used * (15 / 18),  # Split volume proportionally
                'Total Cost': calculate_cost(15, total_volume_used * (15 / 18), dcd_upper_limit) if include_cost else None
            })
            packages.append({
                'Job Nos': job_nos,
                'Total Weight': 6,
                'Total Volume': total_volume_used * (6 / 18),  # Split volume proportionally
                'Total Cost': calculate_cost(6, total_volume_used * (6 / 18), dcd_upper_limit) if include_cost else None
            })
            packages.append({
                'Job Nos': job_nos,
                'Total Weight': 9,
                'Total Volume': total_volume_used * (9 / 18),  # Split volume proportionally
                'Total Cost': calculate_cost(9, total_volume_used * (9 / 18), dcd_upper_limit) if include_cost else None
            })

        elif total_weight_used == 24:
            packages.append({
                'Job Nos': job_nos,
                'Total Weight': 18,
                'Total Volume': total_volume_used * (18 / 24),  # Split volume proportionally
                'Total Cost': calculate_cost(18, total_volume_used * (18 / 24), dcd_upper_limit) if include_cost else None
            })
            packages.append({
                'Job Nos': job_nos,
                'Total Weight': 15,
                'Total Volume': total_volume_used * (15 / 24),  # Split volume proportionally
                'Total Cost': calculate_cost(15, total_volume_used * (15 / 24), dcd_upper_limit) if include_cost else None
            })
            packages.append({
                'Job Nos': job_nos,
                'Total Weight': 6,
                'Total Volume': total_volume_used * (6 / 24),  # Split volume proportionally
                'Total Cost': calculate_cost(6, total_volume_used * (6 / 24), dcd_upper_limit) if include_cost else None
            })
            packages.append({
                'Job Nos': job_nos,
                'Total Weight': 9,
                'Total Volume': total_volume_used * (9 / 24),  # Split volume proportionally
                'Total Cost': calculate_cost(9, total_volume_used * (9 / 24), dcd_upper_limit) if include_cost else None
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
                'Job Nos': job_nos,
                'Total Weight': total_weight_used,
                'Total Volume': total_volume_used,
                'Total Cost': total_cost
            })

        data = data.drop(selected_packages).reset_index(drop=True)

    # Handle smaller weight classes recursively
    for lower_weight_class in [(4.5, 6), (7, 9), (10, 15), (16, 18), (20, 24)]:
        if lower_weight_class[-1] < weight_range[-1]:
            sub_packages, sub_unfulfilled = create_packages_recursive(data, lower_weight_class, carry_volume, include_cost, dcd_upper_limit)
            packages.extend(sub_packages)
            unfulfilled_packages = pd.concat([unfulfilled_packages, sub_unfulfilled])

    return packages, unfulfilled_packages

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
