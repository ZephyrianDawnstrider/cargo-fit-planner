import numpy as np
import pandas as pd
from ortools.linear_solver import pywraplp
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import plotly.graph_objects as go
import os

colors = [
    '#ff0026', '#e66b94', '#dd00ff', '#6600ff', '#8b99e7', '#0095ff', '#00fff2', '#00ff00', '#e5ff00', '#b1ab71',
    '#79725c', '#ff9d00', 'rgba(124, 96, 93, 1)', '#7a2900', '#854242', '#815959', '#f14a4a', '#5a5a5a', '#381010', '#520000'
]

def get_color(queryid, id_val):
    key = f"{queryid}-{id_val}"
    hash_val = abs(hash(key)) % len(colors)
    return colors[hash_val]

def optimize_packages(data, carry_capacity, carry_volume, min_weight_ratio=0.6, min_volume_ratio=0.6):
    required_columns = ['weight_tons', 'volume_cbm']
    if not all(col in data.columns for col in required_columns):
        return [], 0, 0

    solver = pywraplp.Solver.CreateSolver('SCIP')
    if not solver:
        return [], 0, 0

    num_packages = len(data)
    x = [solver.IntVar(0, 1, f'x[{i}]') for i in range(num_packages)]

    total_weight = solver.Sum(data.loc[i, 'weight_tons'] * x[i] for i in range(num_packages))
    total_volume = solver.Sum(data.loc[i, 'volume_cbm'] * x[i] for i in range(num_packages))

    solver.Add(total_weight <= carry_capacity)
    solver.Add(total_volume <= carry_volume)
    solver.Add(total_weight >= min_weight_ratio * carry_capacity)
    solver.Add(total_volume >= min_volume_ratio * carry_volume)

    # Maximize number of packages
    objective = solver.Sum(x[i] for i in range(num_packages))
    solver.Maximize(objective)

    status = solver.Solve()

    if status == pywraplp.Solver.OPTIMAL:
        selected_packages = [i for i in range(num_packages) if x[i].solution_value() > 0.5]
        total_weight_used = sum(data.loc[i, 'weight_tons'] for i in selected_packages)
        total_volume_used = sum(data.loc[i, 'volume_cbm'] for i in selected_packages)
        return selected_packages, total_weight_used, total_volume_used
    else:
        return [], 0, 0

def create_3d_model(container_length, container_breadth, container_height, items, output_path):
    fig = go.Figure()

    # Draw container
    fig.add_trace(go.Mesh3d(
        x=[0, container_length, container_length, 0, 0, container_length, container_length, 0],
        y=[0, 0, container_breadth, container_breadth, 0, 0, container_breadth, container_breadth],
        z=[0, 0, 0, 0, container_height, container_height, container_height, container_height],
        i=[0,0,4,4,0,0,3,3,0,0,1,1],
        j=[1,2,5,6,1,5,2,6,3,7,2,6],
        k=[2,3,6,7,5,4,6,7,7,4,6,5],
        opacity=0.3,
        color='lightblue',
        name='Container'
    ))

    # Define rules for each package type
    rules = {
        'General Goods': {'can_stack_on': True, 'must_be_on_top': False, 'near_exit': False, 'can_rotate': True},
        'Dangerous Goods': {'can_stack_on': False, 'must_be_on_top': False, 'near_exit': True, 'can_rotate': False},
        'Over-Dimension Cargo': {'can_stack_on': True, 'must_be_on_top': False, 'near_exit': False, 'can_rotate': True},
        'Breakable Goods': {'can_stack_on': False, 'must_be_on_top': True, 'near_exit': False, 'can_rotate': False},
        'Temperature-Controlled Goods': {'can_stack_on': False, 'must_be_on_top': False, 'near_exit': True, 'can_rotate': False},
        'Non-Stackable Cargo': {'can_stack_on': False, 'must_be_on_top': False, 'near_exit': False, 'can_rotate': True},
        'Non-Tiltable Cargo': {'can_stack_on': True, 'must_be_on_top': False, 'near_exit': False, 'can_rotate': False}
    }

    # Sort items: breakable last, dangerous/temp first, then by volume descending
    def sort_key(item):
        cargo_type = item.get('CargoType', 'General Goods')
        rule = rules.get(cargo_type, rules['General Goods'])
        priority = 0
        if rule['must_be_on_top']:
            priority = 2  # last
        elif rule['near_exit']:
            priority = 0  # first
        else:
            priority = 1
        volume = float(item.get('Lenght', 1)) * float(item.get('Breadth', 1)) * float(item.get('Height', 1))
        return (priority, -volume)  # higher priority first, then larger volume first

    items.sort(key=sort_key)

    # Initialize height map for stacking
    grid_size = 0.1  # 10 cm grid
    num_x = int(container_length / grid_size) + 1
    num_y = int(container_breadth / grid_size) + 1
    height_map = [[0.0 for _ in range(num_y)] for _ in range(num_x)]

    for item in items:
        l = float(item.get('Lenght', 1)) / 100  # Convert cm to m
        b = float(item.get('Breadth', 1)) / 100
        h = float(item.get('Height', 1)) / 100
        cargo_type = item.get('CargoType', 'General Goods')
        rule = rules.get(cargo_type, rules['General Goods'])

        color = get_color(item.get('queryid'), item.get('id'))

        # Find best position
        best_x, best_y, best_z = None, None, float('inf')
        step = grid_size
        x_range = range(0, int((container_length - l) / step) + 1)
        y_range = range(0, int((container_breadth - b) / step) + 1)

        # For near_exit, prefer low x
        if rule['near_exit']:
            x_range = sorted(x_range, key=lambda ix: ix * step)  # low x first

        for ix in x_range:
            x = ix * step
            for iy in y_range:
                y = iy * step
                # Get max_z in the area
                max_z_here = 0
                start_gx = int(x / grid_size)
                end_gx = int((x + l) / grid_size)
                start_gy = int(y / grid_size)
                end_gy = int((y + b) / grid_size)
                for gx in range(start_gx, end_gx + 1):
                    for gy in range(start_gy, end_gy + 1):
                        if 0 <= gx < num_x and 0 <= gy < num_y:
                            max_z_here = max(max_z_here, height_map[gx][gy])
                # For must_be_on_top, place at highest z
                if rule['must_be_on_top']:
                    max_z_here = container_height - h  # place on top
                # For non-stackable, only at z=0
                elif not rule['can_stack_on'] and max_z_here > 0:
                    continue
                if max_z_here + h <= container_height and max_z_here < best_z:
                    best_z = max_z_here
                    best_x = x
                    best_y = y

        if best_x is not None:
            # Place item
            fig.add_trace(go.Mesh3d(
                x=[best_x, best_x+l, best_x+l, best_x, best_x, best_x+l, best_x+l, best_x],
                y=[best_y, best_y, best_y+b, best_y+b, best_y, best_y, best_y+b, best_y+b],
                z=[best_z, best_z, best_z, best_z, best_z+h, best_z+h, best_z+h, best_z+h],
                i=[0, 0, 0, 1, 4, 4, 2, 6, 4, 0, 3, 7],
                j=[1, 2, 3, 5, 5, 6, 6, 7, 1, 2, 2, 6],
                k=[2, 3, 0, 6, 6, 7, 7, 2, 5, 5, 3, 3],
                color=color,
                opacity=0.7,
                name=f"Q{item.get('queryid')}-I{item.get('id')} ({cargo_type}) L:{l:.1f}m B:{b:.1f}m H:{h:.1f}m W:{item.get('weight_tons', 0):.3f}t"
            ))
            # Update height_map
            new_height = best_z + h
            if not rule['can_stack_on']:
                new_height = container_height  # prevent stacking on top
            for gx in range(int(best_x / grid_size), int((best_x + l) / grid_size) + 1):
                for gy in range(int(best_y / grid_size), int((best_y + b) / grid_size) + 1):
                    if 0 <= gx < num_x and 0 <= gy < num_y:
                        height_map[gx][gy] = new_height

    fig.update_layout(scene=dict(
        xaxis_title='Length (m)',
        yaxis_title='Breadth (m)',
        zaxis_title='Height (m)',
        aspectmode='data'
    ))

    # Add hover event to highlight table rows
    hover_script = """
    <script>
    var plotlyDiv = document.querySelector('.plotly-graph-div');
    if (plotlyDiv) {
        plotlyDiv.on('plotly_hover', function(data) {
            if (data.points && data.points.length > 0) {
                var point = data.points[0];
                var name = point.data.name;
                if (name) {
                    var match = name.match(/Q(\\d+)-I(\\d+)/);
                    if (match) {
                        var queryid = match[1];
                        var id = match[2];
                        window.parent.postMessage({type: 'highlight', queryid: queryid, id: id}, '*');
                    }
                }
            }
        });
        plotlyDiv.on('plotly_unhover', function(data) {
            window.parent.postMessage({type: 'unhighlight'}, '*');
        });
    }
    </script>
    """

    html_content = fig.to_html()
    html_content = html_content.replace('</body>', hover_script + '</body>')
    with open(output_path.replace('.png', '.html'), 'w', encoding='utf-8') as f:
        f.write(html_content)
