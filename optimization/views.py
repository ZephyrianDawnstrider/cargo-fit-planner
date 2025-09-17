from django.shortcuts import render
from django.http import JsonResponse
from .forms import UploadForm
from .models import Dimensions, Containertypes
from .utils import optimize_packages, create_3d_model
import pandas as pd
import json
import os
import logging

logger = logging.getLogger(__name__)

def upload_view(request):
    if request.method == 'POST':
        form = UploadForm(request.POST)
        if form.is_valid():
            container_type = form.cleaned_data['container_type']
            container_sizes = form.cleaned_data['container_size']
            selected_dimensions_ids = form.cleaned_data.get('selected_dimensions', '')
            include_cost = form.cleaned_data['include_cost']

            try:
                # Determine categorytypeid based on container type
                if container_type == 'console':
                    categorytypeid = 7
                elif container_type == 'closed_body_truck':
                    categorytypeid = 8
                else:
                    return render(request, 'optimization/upload.html', {'form': form, 'error': 'Invalid container type selected.'})

                # Handle multiple container sizes
                if not container_sizes:
                    return render(request, 'optimization/upload.html', {'form': form, 'error': 'Please select at least one container size.'})

                containers = []
                total_volume = 0
                total_max_weight = 0

                for container_size in container_sizes:
                    container = Containertypes.objects.filter(
                        categorytypeid=categorytypeid,
                        name=container_size.split(' - ')[0] if ' - ' in container_size else container_size,
                        size=container_size.split(' - ')[1] if ' - ' in container_size else container_size
                    ).first()

                    if container:
                        containers.append(container)
                        total_volume += float(container.volume_cbm)
                        total_max_weight += float(container.maxpayload_kg) / 1000  # Convert to tons
                    else:
                        # Try to find a default container for this category
                        default_container = Containertypes.objects.filter(
                            categorytypeid=categorytypeid
                        ).first()
                        if default_container:
                            containers.append(default_container)
                            total_volume += float(default_container.volume_cbm)
                            total_max_weight += float(default_container.maxpayload_kg) / 1000

                if not containers:
                    return render(request, 'optimization/upload.html', {'form': form, 'error': 'No valid containers found.'})

                # Check if all container sizes for the category are selected
                total_sizes = Containertypes.objects.filter(categorytypeid=categorytypeid).count()
                all_selected = len(container_sizes) == total_sizes

                # Get selected dimensions
                if selected_dimensions_ids:
                    selected_ids = [int(id.strip()) for id in selected_dimensions_ids.split(',') if id.strip()]
                    dimensions = Dimensions.objects.filter(id__in=selected_ids)
                else:
                    dimensions = Dimensions.objects.all()

                # Convert to DataFrame for processing
                data = pd.DataFrame(list(dimensions.values(
                    'queryid', 'id', 'Lenght', 'Breadth', 'Height', 'WeightPerUnit',
                    'TotalUnits', 'PackageType', 'CargoType', 'BasePackageWeight'
                )))

                if data.empty:
                    return render(request, 'optimization/upload.html', {'form': form, 'error': 'No dimensions data available.'})

                # Get selected data
                selected_ids = [int(id.strip()) for id in selected_dimensions_ids.split(',') if id.strip()] if selected_dimensions_ids else []
                selected_data = data[data['id'].isin(selected_ids)] if selected_ids else data

                # Expand data by TotalUnits
                selected_data_expanded = []
                for index, row in selected_data.iterrows():
                    units = int(row['TotalUnits'])
                    for _ in range(units):
                        selected_data_expanded.append({
                            'queryid': row['queryid'],
                            'id': row['id'],
                            'Lenght': row['Lenght'],
                            'Breadth': row['Breadth'],
                            'Height': row['Height'],
                            'WeightPerUnit': row['WeightPerUnit'],
                            'PackageType': row['PackageType'],
                            'CargoType': row['CargoType'],
                            'BasePackageWeight': row['BasePackageWeight'],
                        'weight_tons': (float(row['BasePackageWeight']) / float(row['TotalUnits'])) / 1000,
                        'volume_cbm': (float(row['Lenght']) * float(row['Breadth']) * (float(row['Height']) + (10 if row['CargoType'] == 'Dangerous Goods' else 0))) / 1000000
                        })
                selected_data_expanded = pd.DataFrame(selected_data_expanded)
                logger.info(f"Expanded data to {len(selected_data_expanded)} individual items from {len(selected_data)} selected records.")

                scenarios = []
                if all_selected:
                    # Create one scenario per container size
                    for scenario_idx, container in enumerate(containers):
                        scenario_name = f"{container.name} - {container.size}"
                        # Pack into this container type only
                        containers_used = []
                        remaining_data = selected_data_expanded.copy()
                        logger.info(f"Starting scenario '{scenario_name}' with {len(remaining_data)} items into {container.name} - {container.size}.")
                        container_count = 0
                        while not remaining_data.empty:
                            selected_indices, total_weight, total_volume = optimize_packages(remaining_data, float(container.maxpayload_kg) / 1000, float(container.volume_cbm))
                            if not selected_indices:
                                break
                            selected_items = remaining_data.iloc[selected_indices]
                            container_count += 1
                            containers_used.append({
                                'container': container,
                                'container_number': container_count,
                                'items': selected_items.to_dict('records'),
                                'total_weight': total_weight,
                                'total_volume': total_volume
                            })
                            logger.info(f"Packed container {container.name} - {container.size} instance {container_count} with {len(selected_items)} items, weight {total_weight:.2f} tons, volume {total_volume:.2f} CBM.")
                            remaining_data = remaining_data.drop(selected_indices).reset_index(drop=True)
                        logger.info(f"Scenario '{scenario_name}' complete. Used {len(containers_used)} containers. Remaining items: {len(remaining_data)}.")

                        # Create 3D models for each used container
                        model_images = []
                        for i, cont in enumerate(containers_used):
                            output_path = f'optimization/static/optimization/3d_model_{scenario_idx}_{i}.html'
                            os.makedirs(os.path.dirname(output_path), exist_ok=True)
                            create_3d_model(float(cont['container'].length_m), float(cont['container'].breadth_m), float(cont['container'].height_m), cont['items'], output_path)
                            model_images.append(f'optimization/3d_model_{scenario_idx}_{i}.html')

                        # Calculate summary
                        total_weight_used = sum(c['total_weight'] for c in containers_used)
                        total_volume_used = sum(c['total_volume'] for c in containers_used)
                        num_containers = len(containers_used)
                        num_remaining = len(remaining_data)
                        total_max_weight = num_containers * (float(container.maxpayload_kg) / 1000) if container.maxpayload_kg else 0
                        total_max_volume = num_containers * float(container.volume_cbm) if container.volume_cbm else 0
                        weight_util = (total_weight_used / total_max_weight) * 100 if total_max_weight > 0 else 0
                        volume_util = (total_volume_used / total_max_volume) * 100 if total_max_volume > 0 else 0

                        summary_name = f"{scenario_name}: {num_containers} containers, {weight_util:.1f}% weight, {volume_util:.1f}% volume, {num_remaining} remaining"

                        scenarios.append({
                            'name': summary_name,
                            'containers_used': containers_used,
                            'remaining_items': remaining_data.to_dict('records') if not remaining_data.empty else [],
                            'model_images': model_images
                        })
                else:
                    # Single scenario with selected containers
                    scenario_name = 'Selected Containers'
                    sorted_containers = sorted(containers, key=lambda c: float(c.volume_cbm))

                    # Pack into containers
                    containers_used = []
                    remaining_data = selected_data_expanded.copy()
                    logger.info(f"Starting scenario '{scenario_name}' with {len(remaining_data)} items into {len(sorted_containers)} container types.")
                    for container in sorted_containers:
                        container_count = 0
                        while not remaining_data.empty:
                            selected_indices, total_weight, total_volume = optimize_packages(remaining_data, float(container.maxpayload_kg) / 1000, float(container.volume_cbm))
                            if not selected_indices:
                                break
                            selected_items = remaining_data.iloc[selected_indices]
                            container_count += 1
                            containers_used.append({
                                'container': container,
                                'container_number': container_count,
                                'items': selected_items.to_dict('records'),
                                'total_weight': total_weight,
                                'total_volume': total_volume
                            })
                            logger.info(f"Packed container {container.name} - {container.size} instance {container_count} with {len(selected_items)} items, weight {total_weight:.2f} tons, volume {total_volume:.2f} CBM.")
                            remaining_data = remaining_data.drop(selected_indices).reset_index(drop=True)
                    logger.info(f"Scenario '{scenario_name}' complete. Used {len(containers_used)} containers. Remaining items: {len(remaining_data)}.")

                    # Create 3D models for each used container
                    model_images = []
                    for i, cont in enumerate(containers_used):
                        output_path = f'optimization/static/optimization/3d_model_0_{i}.html'
                        os.makedirs(os.path.dirname(output_path), exist_ok=True)
                        create_3d_model(float(cont['container'].length_m), float(cont['container'].breadth_m), float(cont['container'].height_m), cont['items'], output_path)
                        model_images.append(f'optimization/3d_model_0_{i}.html')

                    scenarios.append({
                        'name': scenario_name,
                        'containers_used': containers_used,
                        'remaining_items': remaining_data.to_dict('records') if not remaining_data.empty else [],
                        'model_images': model_images
                    })

                # Create container names string for display
                container_names = [f"{c.name} - {c.size}" for c in containers]
                selected_containers_str = ", ".join(container_names)

                context = {
                    'scenarios': scenarios,
                    'selected_container': selected_containers_str,
                    'max_weight': total_max_weight,
                    'container_volume': total_volume
                }

                return render(request, 'optimization/results.html', context)

            except Exception as e:
                return render(request, 'optimization/upload.html', {'form': form, 'error': str(e)})
    else:
        form = UploadForm()

    # Get dimensions for display
    dimensions = Dimensions.objects.all()
    context = {
        'form': form,
        'dimensions': dimensions
    }
    return render(request, 'optimization/upload.html', context)


def get_container_sizes(request, categorytypeid):
    containers = Containertypes.objects.filter(categorytypeid=categorytypeid)
    sizes = [f"{c.name} - {c.size}" for c in containers]
    return JsonResponse({'sizes': sizes})
