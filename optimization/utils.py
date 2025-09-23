import numpy as np
import pandas as pd
from ortools.linear_solver import pywraplp
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import plotly.graph_objects as go
import os

colors = [
    '#ff0026', '#e66b94', '#dd00ff', '#6600ff', '#8b99e7', '#0095ff', '#00fff2', '#00ff00', "#4a5201", "#7a6e00",
    '#79725c', '#ff9d00', 'rgba(124, 96, 93, 1)', '#7a2900', '#854242', '#815959', '#f14a4a', '#5a5a5a', '#381010', '#520000'
]

def get_color(queryid, id_val):
    key = f"{queryid}-{id_val}"
    hash_val = abs(hash(key)) % len(colors)
    return colors[hash_val]

def optimize_packages(data, carry_capacity, carry_volume, min_weight_ratio=0.9, min_volume_ratio=0.9):
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

def mixed_bin_packing(cargo_df, available_containers, output_dir):
    """
    Perform mixed bin packing using available container types to minimize number of containers.
    Heuristic: Sort containers by volume descending, greedily pack into largest suitable container.
    """
    import os
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Starting mixed_bin_packing function")
    logger.info(f"Input: cargo_df shape {cargo_df.shape}, available_containers count {len(available_containers)}, output_dir {output_dir}")

    # Sort containers by volume descending
    available_containers = sorted(available_containers, key=lambda c: float(c.volume_cbm), reverse=True)
    logger.info(f"Sorted available_containers by volume descending: {[f'{c.name}-{c.size}:{c.volume_cbm}' for c in available_containers]}")

    containers_used = []
    remaining_data = cargo_df.copy()
    container_counter = 0
    model_images = []
    logger.info(f"Initial remaining_data shape: {remaining_data.shape}")

    while not remaining_data.empty:
        logger.info(f"Loop start: remaining_data shape {remaining_data.shape}")
        total_remaining_weight = remaining_data['weight_tons'].sum()
        total_remaining_volume = remaining_data['volume_cbm'].sum()
        logger.info(f"Total remaining weight: {total_remaining_weight} tons, volume: {total_remaining_volume} CBM")

        # Choose the best container: the one that can pack the most items
        best_container = None
        max_packed = 0
        for c in available_containers:
            selected_indices, _, _ = optimize_packages(remaining_data, float(c.maxpayload_kg) / 1000, float(c.volume_cbm))
            num_packed = len(selected_indices)
            if num_packed > max_packed:
                max_packed = num_packed
                best_container = c
        if best_container:
            chosen = best_container
            logger.info(f"Chosen container (packs most items: {max_packed}): {chosen.name}-{chosen.size}")
        else:
            # Fallback, though unlikely
            chosen = available_containers[0]
            logger.info(f"Chosen container (fallback): {chosen.name}-{chosen.size}")

        # Pack subset into chosen
        logger.info(f"Calling optimize_packages with capacity weight {float(chosen.maxpayload_kg) / 1000}, volume {float(chosen.volume_cbm)}")
        selected_indices, _, _ = optimize_packages(remaining_data, float(chosen.maxpayload_kg) / 1000, float(chosen.volume_cbm))
        logger.info(f"optimize_packages returned selected_indices: {len(selected_indices) if selected_indices else 0}")
        if not selected_indices:
            logger.info("No items selected, breaking loop")
            break

        selected_items = remaining_data.iloc[selected_indices]
        logger.info(f"Selected items shape: {selected_items.shape}")
        container_counter += 1
        items_list = selected_items.to_dict('records')
        logger.info(f"Items list length: {len(items_list)}")
        for item in items_list:
            item['color'] = get_color(item['queryid'], item['id'])
            logger.debug(f"Assigned color to item {item['queryid']}-{item['id']}: {item['color']}")

        # Create 3D model
        output_path = f'{output_dir}/3d_model_mixed_{container_counter}.html'
        logger.info(f"Creating 3D model at {output_path}")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        placed_items = create_3d_model(float(chosen.length_m), float(chosen.breadth_m), float(chosen.height_m), items_list, output_path)
        logger.info(f"3D model created, placed_items length: {len(placed_items)}")

        total_weight_placed = sum(item['weight_tons'] for item in placed_items)
        total_volume_placed = sum(item['volume_cbm'] for item in placed_items)
        logger.info(f"Placed total weight: {total_weight_placed}, volume: {total_volume_placed}")

        containers_used.append({
            'container': chosen,
            'container_number': container_counter,
            'items': placed_items,
            'total_weight': total_weight_placed,
            'total_volume': total_volume_placed
        })
        model_images.append(f'optimization/3d_model_mixed_{container_counter}.html')
        logger.info(f"Added container {container_counter} to used list")

        # Update remaining
        logger.info(f"Dropping selected indices: {selected_indices}")
        remaining_data = remaining_data.drop(selected_indices).reset_index(drop=True)
        unplaced = [item for item in items_list if item not in placed_items]
        logger.info(f"Unplaced items: {len(unplaced)}")
        if unplaced:
            unplaced_df = pd.DataFrame(unplaced)
            logger.info(f"Concatenating unplaced_df shape {unplaced_df.shape} to remaining_data")
            remaining_data = pd.concat([remaining_data, unplaced_df], ignore_index=True)
        logger.info(f"End of loop: remaining_data shape {remaining_data.shape}")

    logger.info(f"Mixed bin packing complete: used {len(containers_used)} containers, remaining items {len(remaining_data)}")
    return containers_used, model_images, remaining_data

def create_3d_model(container_length, container_breadth, container_height, items, output_path, animation=False):
    placed_items = []
    fig = go.Figure()

    # Draw container
    fig.add_trace(go.Mesh3d(
        x=[0, container_length, container_length, 0, 0, container_length, container_length, 0],
        y=[0, 0, container_breadth, container_breadth, 0, 0, container_breadth, container_breadth],
        z=[0, 0, 0, 0, container_height, container_height, container_height, container_height],
        i=[0,0,4,4,0,0,3,3,0,0,1,1],
        j=[1,2,5,6,1,5,2,6,3,7,2,6],
        k=[2,3,6,7,5,4,6,7,7,4,6,5],
        opacity=0.1,
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
        # 'Non-Stackable Cargo': {'can_stack_on': False, 'must_be_on_top': True, 'near_exit': False, 'can_rotate': True},
        'Non-Stackable': {'can_stack_on': False, 'must_be_on_top': True, 'near_exit': False, 'can_rotate': True},
        'Non-Tiltable Cargo': {'can_stack_on': True, 'must_be_on_top': False, 'near_exit': False, 'can_rotate': False}
    }

    # Sort items: breakable and non-stackable last, dangerous/temp first, then by volume descending
    def sort_key(item):
        cargo_type = item.get('CargoType', 'General Goods')
        rule = rules.get(cargo_type, rules['General Goods'])
        priority = 1
        if rule['near_exit']:
            priority = 0  # first
        elif rule['must_be_on_top'] or not rule['can_stack_on']:
            priority = 2  # last
        volume = float(item.get('Lenght', 1)) * float(item.get('Breadth', 1)) * float(item.get('Height', 1))
        return (priority, -volume)  # higher priority first, then larger volume first

    items.sort(key=sort_key)

    # Initialize height map for stacking
    grid_size = 0.1  # 10 cm grid
    num_x = int(container_length / grid_size) + 1
    num_y = int(container_breadth / grid_size) + 1
    height_map = [[0.0 for _ in range(num_y)] for _ in range(num_x)]

    # List to track placed boxes for collision detection
    placed_boxes = []
    packing_order = 0

    def boxes_overlap(box1, box2):
        """Check if two boxes overlap in 3D space."""
        return not (
            box1['xmax'] <= box2['xmin'] or box1['xmin'] >= box2['xmax'] or
            box1['ymax'] <= box2['ymin'] or box1['ymin'] >= box2['ymax'] or
            box1['zmax'] <= box2['zmin'] or box1['zmin'] >= box2['zmax']
        )

    for item in items:
        l = float(item.get('Lenght', 1)) / 100  # Convert cm to m
        b = float(item.get('Breadth', 1)) / 100
        h = float(item.get('Height', 1)) / 100
        cargo_type = item.get('CargoType', 'General Goods')
        rule = rules.get(cargo_type, rules['General Goods'])

        color = item.get('color', get_color(item.get('queryid'), item.get('id')))

        # Find best position
        best_x, best_y, best_z = None, None, float('inf')
        step = grid_size
        x_range = range(0, int((container_length - l) / step) + 1)
        y_range = range(0, int((container_breadth - b) / step) + 1)

        # For near_exit, prefer low x and low y
        if rule['near_exit']:
            x_range = sorted(x_range, key=lambda ix: ix * step)  # low x first
            y_range = sorted(y_range, key=lambda iy: iy * step)  # low y first

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
                min_z_here = float('inf')
                for gx in range(start_gx, end_gx + 1):
                    for gy in range(start_gy, end_gy + 1):
                        if 0 <= gx < num_x and 0 <= gy < num_y:
                            z_val = height_map[gx][gy]
                            max_z_here = max(max_z_here, z_val)
                            min_z_here = min(min_z_here, z_val)
                # Skip if the surface is not flat
                if min_z_here != max_z_here:
                    continue
                # For dangerous goods, ensure on ground and nothing below
                if rule['near_exit'] and max_z_here > 0:
                    continue  # skip if not on ground
                # For must_be_on_top, place at highest z only if not on non-stackable
                if rule['must_be_on_top']:
                    if max_z_here < container_height:
                        max_z_here = container_height - h  # place on top
                    else:
                        continue  # can't place on non-stackable
                if max_z_here + h <= container_height and max_z_here < best_z:
                    # Check for overlap with placed boxes
                    proposed_box = {
                        'xmin': x, 'xmax': x + l,
                        'ymin': y, 'ymax': y + b,
                        'zmin': max_z_here, 'zmax': max_z_here + h
                    }
                    overlap = False
                    for placed_box in placed_boxes:
                        if boxes_overlap(proposed_box, placed_box):
                            overlap = True
                            break
                    if not overlap:
                        best_z = max_z_here
                        best_x = x
                        best_y = y
        if best_x is not None:
            packing_order += 1
            placed_items.append(item)
            # Place item
            fig.add_trace(go.Mesh3d(
                x=[best_x, best_x+l, best_x+l, best_x, best_x, best_x+l, best_x+l, best_x],
                y=[best_y, best_y, best_y+b, best_y+b, best_y, best_y, best_y+b, best_y+b],
                z=[best_z, best_z, best_z, best_z, best_z+h, best_z+h, best_z+h, best_z+h],
                i=[0, 0, 0, 1, 4, 4, 2, 6, 4, 0, 3, 7],
                j=[1, 2, 3, 5, 5, 6, 6, 7, 1, 2, 2, 6],
                k=[2, 3, 0, 6, 6, 7, 7, 2, 5, 5, 3, 3],
                color=color,
                opacity=1.0,
                hoverinfo='text',
                hovertext=f"Packing Order: {packing_order}<br>Query ID: {item.get('queryid')}<br>ID: {item.get('id')}<br>Package Type: {item.get('PackageType')}<br>Cargo Type: {cargo_type}<br>Dimensions: {l*100:.0f}×{b*100:.0f}×{h*100:.0f} cm<br>Weight: {item.get('weight_tons', 0):.3f} tons<br>Volume: {item.get('volume_cbm', 0):.3f} CBM",
                name=f"Q{item.get('queryid')}-I{item.get('id')}"
            ))

            if animation:
                # Save animation step
                fig.update_layout(title=f"Packing Step {packing_order}")
                step_path = output_path.replace('.html', f'_step_{packing_order}.html')
                html_content = fig.to_html()
                html_content = html_content.replace('</body>', hover_script + '</body>')
                with open(step_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
            # Update height_map
            new_height = best_z + h
            if not rule['can_stack_on']:
                new_height = container_height  # prevent stacking on top
            for gx in range(int(best_x / grid_size), int((best_x + l) / grid_size) + 1):
                for gy in range(int(best_y / grid_size), int((best_y + b) / grid_size) + 1):
                    if 0 <= gx < num_x and 0 <= gy < num_y:
                        height_map[gx][gy] = new_height

            # Add to placed boxes
            placed_boxes.append({
                'xmin': best_x, 'xmax': best_x + l,
                'ymin': best_y, 'ymax': best_y + b,
                'zmin': best_z, 'zmax': best_z + h
            })

    # Add hover and click events to highlight table rows
    hover_script = """
    <script>
    var plotlyDiv = document.querySelector('.plotly-graph-div');
    if (plotlyDiv) {
        plotlyDiv.on('plotly_hover', function(data) {
            if (data.points && data.points.length > 0) {
                var point =  data.points[0];
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
        plotlyDiv.on('plotly_click', function(data) {
            if (data.points && data.points.length > 0) {
                var point = data.points[0];
                var name = point.data.name;
                if (name) {
                    var match = name.match(/Q(\\d+)-I(\\d+)/);
                    if (match) {
                        var queryid = match[1];
                        var id = match[2];
                        window.parent.postMessage({type: 'click', queryid: queryid, id: id}, '*');
                    }
                }
            }
        });

        // Listen for messages from parent
        window.addEventListener('message', function(event) {
            if (event.data.type === 'highlight') {
                const { queryid, id } = event.data;
                // Find and highlight the trace
                const traces = plotlyDiv.data;
                traces.forEach((trace, index) => {
                    if (trace.name === `Q${queryid}-I${id}`) {
                        Plotly.restyle(plotlyDiv, {opacity: 1}, [index]);
                    } else {
                        Plotly.restyle(plotlyDiv, {opacity: 0.3}, [index]);
                    }
                });
            }
        });
    }
    </script>
    """

    fig.update_layout(scene=dict(
        xaxis_title='Length (m)',
        yaxis_title='Breadth (m)',
        zaxis_title='Height (m)',
        aspectmode='data'
    ))

    html_content = fig.to_html()
    html_content = html_content.replace('</body>', hover_script + '</body>')
    with open(output_path.replace('.png', '.html'), 'w', encoding='utf-8') as f:
        f.write(html_content)
    return placed_items
