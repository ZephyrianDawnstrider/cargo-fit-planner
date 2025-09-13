from django.shortcuts import render
from django.http import JsonResponse
from .forms import UploadForm
from .models import Dimensions, Containertypes
from .utils import convert_weights, analyze_weight_classes
import pandas as pd
import json

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

                # Get selected dimensions
                if selected_dimensions_ids:
                    selected_ids = [int(id.strip()) for id in selected_dimensions_ids.split(',') if id.strip()]
                    dimensions = Dimensions.objects.filter(id__in=selected_ids)
                else:
                    dimensions = Dimensions.objects.all()

                # Convert to DataFrame for processing
                data = pd.DataFrame(list(dimensions.values(
                    'id', 'Lenght', 'Breadth', 'Height', 'WeightPerUnit',
                    'TotalUnits', 'PackageType', 'CargoType', 'BasePackageWeight'
                )))

                if data.empty:
                    return render(request, 'optimization/upload.html', {'form': form, 'error': 'No dimensions data available.'})

                # Calculate weight and volume
                data = convert_weights(data)

                # Use combined container volume and max payload
                fulfilled_files, unfulfilled_files, best_class = analyze_weight_classes(
                    data, total_volume, include_cost, total_max_weight
                )

                # Prepare data for template
                best_packages = []
                total_cost_best_class = 0
                if fulfilled_files:
                    for weight_class, packages in fulfilled_files.items():
                        if weight_class == best_class:
                            for pkg in packages:
                                best_packages.append({
                                    'console_data_html': pkg['Console Data'].to_html(index=False, classes='min-w-full table-auto border-collapse border border-gray-300 text-sm'),
                                    'total_weight': pkg['Total Weight'],
                                    'total_volume': pkg['Total Volume'],
                                    'total_cost': pkg['Total Cost']
                                })
                                if pkg['Total Cost']:
                                    total_cost_best_class += pkg['Total Cost']

                # Unfulfilled for best class
                unfulfilled_best = []
                for wc, unfulfilled in unfulfilled_files:
                    if wc == best_class:
                        unfulfilled_best.append({
                            'weight_class': wc,
                            'data_html': unfulfilled.to_html(index=False, classes='min-w-full table-auto border-collapse border border-gray-300 text-sm') if not unfulfilled.empty else '<p>No unfulfilled packages.</p>'
                        })

                # All fulfilled
                all_fulfilled = []
                for idx, (weight_class, packages) in enumerate(fulfilled_files.items()):
                    for pkg in packages:
                        all_fulfilled.append({
                            'package_idx': idx + 1,
                            'weight_class': weight_class,
                            'console_data_html': pkg['Console Data'].to_html(index=False, classes='min-w-full table-auto border-collapse border border-gray-300 text-sm'),
                            'total_weight': pkg['Total Weight'],
                            'total_volume': pkg['Total Volume'],
                            'total_cost': pkg['Total Cost']
                        })

                # All unfulfilled
                all_unfulfilled = []
                for weight_class, unfulfilled in unfulfilled_files:
                    all_unfulfilled.append({
                        'weight_class': weight_class,
                        'data_html': unfulfilled.to_html(index=False, classes='min-w-full table-auto border-collapse border border-gray-300 text-sm') if not unfulfilled.empty else '<p>No unfulfilled packages.</p>'
                    })

                # Comparative report
                comparative_data = []
                for weight_class, packages in fulfilled_files.items():
                    total_weight = sum(pkg['Total Weight'] for pkg in packages)
                    total_volume = sum(pkg['Total Volume'] for pkg in packages)
                    total_cost = sum(pkg['Total Cost'] if pkg['Total Cost'] is not None else 0 for pkg in packages)

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

                comparative_df = pd.DataFrame(comparative_data)
                comparative_html = comparative_df.to_html(index=False, classes='min-w-full table-auto border-collapse border border-gray-300 text-sm')

                # Create container names string for display
                container_names = [f"{c.name} - {c.size}" for c in containers]
                selected_containers_str = ", ".join(container_names)

                context = {
                    'best_class': best_class,
                    'total_cost_best_class': total_cost_best_class,
                    'best_packages': best_packages,
                    'unfulfilled_best': unfulfilled_best,
                    'all_fulfilled': all_fulfilled,
                    'all_unfulfilled': all_unfulfilled,
                    'comparative_html': comparative_html,
                    'total_unfulfilled_count': len(unfulfilled_files),
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


def get_container_sizes(request, container_type):
    if container_type == 'console':
        categorytypeid = 7
    elif container_type == 'closed_body_truck':
        categorytypeid = 8
    else:
        return JsonResponse({'error': 'Invalid container type'}, status=400)

    containers = Containertypes.objects.filter(categorytypeid=categorytypeid)
    sizes = [f"{c.name} - {c.size}" for c in containers]
    return JsonResponse({'sizes': sizes})
